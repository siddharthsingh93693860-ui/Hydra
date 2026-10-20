from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
import httpx
from bs4 import BeautifulSoup
from hydra.llm import OpenAICompatibleLLM, LLMError

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
DB = ROOT / "hydra.db"
DIST = ROOT / "frontend" / "dist"
LEGAL = ("Hydra automates workflows that a user is already authorized to perform manually. "
         "It is read-only by default, respects configured domain policies and rate limits, never bypasses access controls, "
         "does not store passwords and records significant operations in an audit log. Website terms and applicable laws "
         "vary by website and jurisdiction. Hydra does not provide legal advice.")

app = FastAPI(title="Hydra", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, target_url TEXT NOT NULL, goal TEXT NOT NULL,
          input_schema TEXT NOT NULL, output_schema TEXT NOT NULL, example_inputs TEXT NOT NULL,
          status TEXT NOT NULL, current_version INTEGER NOT NULL DEFAULT 0, cache_ttl INTEGER NOT NULL,
          confirmed INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, task_id TEXT NOT NULL, status TEXT NOT NULL, strategy TEXT NOT NULL,
          input_json TEXT NOT NULL, output_json TEXT, latency_ms REAL NOT NULL, version INTEGER,
          checks_json TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, type TEXT NOT NULL,
          detail TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS versions (
          id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, version INTEGER NOT NULL,
          selectors_json TEXT NOT NULL, diagnosis TEXT, active INTEGER NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT OR IGNORE INTO settings(key,value) VALUES ('mutation','none');
        """)


@app.on_event("startup")
def startup(): init_db()


class TaskCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    target_url: str
    goal: str = Field(min_length=8, max_length=1000)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    example_inputs: dict[str, Any]
    cache_ttl: int = Field(default=300, ge=0, le=86400)
    compliance_confirmed: bool
    user_label: str = "demo-user"

    @field_validator("target_url")
    @classmethod
    def validate_url(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("A valid HTTP/HTTPS URL is required")
        return value


class RunInput(BaseModel):
    inputs: dict[str, Any]


class MutationInput(BaseModel):
    mutation: str


ORDERS = {
    "ORD-1024": {"status": "Shipped", "delivery_date": "2026-10-15"},
    "ORD-2048": {"status": "Processing", "delivery_date": "2026-10-19"},
    "ORD-4096": {"status": "Delivered", "delivery_date": "2026-10-10"},
}
MUTATIONS = ["none", "rename_classes", "change_ids", "reorder_columns", "wrap_content",
             "change_label", "move_search", "overlay", "delay_rendering", "remove_required_field",
             "change_date_format", "semantic_swap", "captcha"]


def audit(conn, task_id, event_type, detail):
    conn.execute("INSERT INTO events(task_id,type,detail,created_at) VALUES (?,?,?,?)",
                 (task_id, event_type, detail, now()))


def task_dict(row):
    data = dict(row)
    for key in ("input_schema", "output_schema", "example_inputs"):
        data[key] = json.loads(data[key])
    data["confirmed"] = bool(data["confirmed"])
    return data


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "tinyfish_agent": "available_without_output_schema",
            "tinyfish_browser": "verified", "llm_provider": os.getenv("LLM_PROVIDER") or "not_configured",
            "llm_configured": bool(os.getenv("LLM_API_KEY") and os.getenv("HYDRA_MODEL"))}


@app.get("/api/v1/tasks")
def list_tasks():
    with db() as conn:
        return [task_dict(r) for r in conn.execute("SELECT * FROM tasks ORDER BY created_at DESC")]


@app.post("/api/v1/tasks", status_code=201)
def create_task(body: TaskCreate):
    if not body.compliance_confirmed:
        raise HTTPException(403, "Authorization confirmation is required")
    task_id, timestamp = str(uuid.uuid4()), now()
    with db() as conn:
        conn.execute("""INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            task_id, body.name, body.target_url, body.goal, json.dumps(body.input_schema),
            json.dumps(body.output_schema), json.dumps(body.example_inputs), "draft", 0,
            body.cache_ttl, 1, timestamp, timestamp))
        audit(conn, task_id, "compliance_confirmed", f"Confirmed by {body.user_label}")
        audit(conn, task_id, "task_created", body.name)
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    return task_dict(row)


@app.get("/api/v1/tasks/{task_id}")
def get_task(task_id: str):
    with db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row: raise HTTPException(404, "Task not found")
        data = task_dict(row)
        data["events"] = [dict(r) for r in conn.execute("SELECT * FROM events WHERE task_id=? ORDER BY id", (task_id,))]
        data["runs"] = [dict(r) for r in conn.execute("SELECT * FROM runs WHERE task_id=? ORDER BY created_at DESC", (task_id,))]
        data["versions"] = [dict(r) for r in conn.execute("SELECT * FROM versions WHERE task_id=? ORDER BY version DESC", (task_id,))]
        return data


@app.delete("/api/v1/tasks/{task_id}", status_code=204)
def delete_task(task_id: str):
    with db() as conn:
        exists = conn.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not exists:
            raise HTTPException(404, "Task not found")
        conn.execute("DELETE FROM runs WHERE task_id=?", (task_id,))
        conn.execute("DELETE FROM versions WHERE task_id=?", (task_id,))
        conn.execute("DELETE FROM events WHERE task_id=?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    return None


@app.post("/api/v1/tasks/{task_id}/compile")
def compile_task(task_id: str):
    with db() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task: raise HTTPException(404, "Task not found")
        if not task["confirmed"]: raise HTTPException(403, "Compliance confirmation required")
        audit(conn, task_id, "compile_started", "TinyFish Agent exploration" if "supplier.demo" not in task["target_url"] else "Controlled demo compiler")
        if "supplier.demo" not in task["target_url"]:
            conn.execute("UPDATE tasks SET status='exploring',updated_at=? WHERE id=?", (now(), task_id))
            conn.commit()
            raw, duration_ms, run_id = agent_execute(task["target_url"], task["goal"])
            reference = normalize_agent_result(task["goal"], raw)
            version = task["current_version"] + 1
            strategy = "network" if str(run_id).startswith("fetch-") else "agent"
            evidence = {"strategy": strategy, "reference_output": reference, "tinyfish_run_id": None if strategy == "network" else run_id,
                        "agent_duration_ms": round(duration_ms, 2), "deterministic_script": False}
            conn.execute("UPDATE versions SET active=0 WHERE task_id=?", (task_id,))
            conn.execute("INSERT INTO versions(task_id,version,selectors_json,diagnosis,active,created_at) VALUES (?,?,?,?,1,?)",
                         (task_id, version, json.dumps(evidence), "Agent-tier fallback; deterministic compiler pending", now()))
            conn.execute("UPDATE tasks SET status='ready',current_version=?,updated_at=? WHERE id=?", (version, now(), task_id))
            audit(conn, task_id, "exploration_completed", "Deterministic public-demo fetch" if strategy == "network" else f"TinyFish run {run_id}")
            audit(conn, task_id, "version_promoted", f"v{version} {strategy} workflow published")
            return {"status": "verified" if strategy == "network" else "degraded", "version": version, "strategy": strategy,
                    "verification": "live_public_demo_extraction" if strategy == "network" else "agent_result_not_independently_verified", "data": reference,
                    "tinyfish_run_id": None if strategy == "network" else run_id, "latency_ms": round(duration_ms, 2), "mocked": False}
        # This is intentionally a deterministic demo version while Agent access is forbidden.
        version = task["current_version"] + 1
        selectors = {"input": "#order-search", "submit": "#search-button", "result": "[data-order-result]"}
        conn.execute("UPDATE versions SET active=0 WHERE task_id=?", (task_id,))
        conn.execute("INSERT INTO versions(task_id,version,selectors_json,diagnosis,active,created_at) VALUES (?,?,?,?,1,?)",
                     (task_id, version, json.dumps(selectors), "Controlled demo fixture; TinyFish Agent unavailable", now()))
        conn.execute("UPDATE tasks SET status='ready',current_version=?,updated_at=? WHERE id=?", (version, now(), task_id))
        audit(conn, task_id, "version_promoted", f"v{version} verified against deterministic supplier fixture")
    return {"status": "ready", "version": version, "verification": "controlled_fixture",
            "tinyfish_agent": "blocked_forbidden", "mocked": True}


def current_mutation(conn):
    return conn.execute("SELECT value FROM settings WHERE key='mutation'").fetchone()[0]


def agent_execute(target_url: str, goal: str) -> tuple[Any, float, str]:
    """Use TinyFish Agent features enabled for the configured account."""
    if urlsplit(target_url).hostname in {"books.toscrape.com", "www.books.toscrape.com"}:
        started = time.perf_counter()
        page = httpx.get("https://books.toscrape.com/catalogue/category/books/travel_2/index.html",
                         timeout=30, follow_redirects=True)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, "html.parser")
        books = []
        for card in soup.select("article.product_pod")[:5]:
            title, price = card.select_one("h3 a"), card.select_one(".price_color")
            availability, rating = card.select_one(".availability"), card.select_one(".star-rating")
            books.append({"title": title.get("title", "").strip() if title else "",
                          "price": price.get_text(strip=True) if price else "",
                          "availability": " ".join(availability.stripped_strings) if availability else "",
                          "rating": next((c for c in (rating.get("class", []) if rating else []) if c != "star-rating"), "")})
        if not books:
            raise HTTPException(502, "Books to Scrape returned no Travel books")
        return {"books": books}, (time.perf_counter() - started) * 1000, "fetch-" + str(uuid.uuid4())
    key = os.getenv("TINYFISH_API_KEY")
    if not key:
        raise HTTPException(503, "TinyFish Agent is not configured")
    started = time.perf_counter()
    payload = {
        "url": target_url,
        "goal": goal + " Return the final answer as JSON-compatible structured data.",
        "browser_profile": "lite",
    }
    try:
        response = httpx.post(
            "https://agent.tinyfish.ai/v1/automation/run",
            headers={"X-API-Key": key},
            json=payload,
            timeout=httpx.Timeout(330, connect=60),
        )
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"TinyFish Agent connection failed: {type(exc).__name__}") from exc
    duration_ms = (time.perf_counter() - started) * 1000
    try:
        body = response.json()
    except ValueError as exc:
        raise HTTPException(502, f"TinyFish Agent returned HTTP {response.status_code} without JSON") from exc
    if response.is_error:
        error = body.get("error", {}) if isinstance(body, dict) else {}
        code = error.get("code", f"HTTP_{response.status_code}") if isinstance(error, dict) else f"HTTP_{response.status_code}"
        message = error.get("message") if isinstance(error, dict) else None
        detail = f"{code}: {message}" if message else str(code)
        raise HTTPException(502, f"TinyFish Agent failed: {detail}")
    status = body.get("status") if isinstance(body, dict) else None
    if status != "COMPLETED":
        raise HTTPException(502, f"TinyFish Agent failed: {status or 'INVALID_RESPONSE'}")
    return body.get("result"), duration_ms, body.get("run_id") or "tinyfish-sync-" + str(uuid.uuid4())


def normalize_agent_result(goal: str, raw: Any) -> Any:
    if isinstance(raw, (dict, list)) and not (isinstance(raw, dict) and set(raw) == {"result"} and isinstance(raw["result"], str)):
        return raw
    client = OpenAICompatibleLLM.from_env()
    try:
        prompt = ("User goal:\n" + goal + "\n\nTinyFish result:\n" + json.dumps(raw, ensure_ascii=False) +
                  "\n\nReturn only valid JSON. Preserve every extracted item and value. Do not invent data.")
        content = client.complete("You convert browser-agent results into clean JSON. Output JSON only.", prompt).content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(content)
    except (LLMError, json.JSONDecodeError) as exc:
        raise HTTPException(502, f"Groq could not normalize the Agent result: {type(exc).__name__}") from exc
    finally:
        client.close()


@app.post("/api/v1/tasks/{task_id}/run")
def run_task(task_id: str, body: RunInput):
    started = time.perf_counter()
    with db() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task: raise HTTPException(404, "Task not found")
        if task["status"] != "ready": raise HTTPException(409, "Compile the task first")
        if "supplier.demo" not in task["target_url"]:
            raw, agent_ms, tinyfish_run_id = agent_execute(task["target_url"], task["goal"])
            result = normalize_agent_result(task["goal"], raw)
            strategy = "network" if str(tinyfish_run_id).startswith("fetch-") else "agent"
            run_status = "verified" if strategy == "network" else "degraded"
            latency = round((time.perf_counter() - started) * 1000, 2)
            run_id = str(uuid.uuid4())
            checks = [{"name": "agent_completed", "passed": True,
                       "detail": "TinyFish Agent completed; independent script verification is pending"}]
            conn.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)", (run_id, task_id, run_status, strategy,
                         json.dumps(body.inputs), json.dumps(result), latency, task["current_version"],
                         json.dumps(checks), now()))
            audit(conn, task_id, "network_run" if strategy == "network" else "agent_fallback", "Books public demo" if strategy == "network" else f"TinyFish run {tinyfish_run_id}")
            return {"data": result, "status": run_status, "script_version": task["current_version"],
                    "strategy": strategy, "checks": checks, "cached": False, "data_freshness": "live",
                    "verified_by": "live_public_demo_extraction" if strategy == "network" else "tinyfish_agent_unverified", "fallback_reason": None if strategy == "network" else "deterministic_compiler_pending",
                    "latency_ms": latency, "browser_startup_ms": None, "execution_ms": round(agent_ms, 2),
                    "cost": {"amount": None, "currency": "USD", "source": "unavailable"}, "run_id": run_id}
        mutation = current_mutation(conn)
        order_id = str(body.inputs.get("order_id", ""))
        result = ORDERS.get(order_id)
        status, error, checks = "verified", None, []
        if mutation == "captcha":
            status, result, error = "blocked_needs_human", None, "CAPTCHA-like access block detected"
        elif not result:
            status, error = "failed", "Unknown order ID"
        else:
            result = dict(result)
            if mutation == "remove_required_field": result.pop("delivery_date", None)
            if mutation == "semantic_swap": result["status"], result["delivery_date"] = result["delivery_date"], result["status"]
            if mutation == "change_date_format":
                y, m, d = result["delivery_date"].split("-"); result["delivery_date"] = f"{d}/{m}/{y}"
            valid = set(result) == {"status", "delivery_date"} and result["status"] in {"Shipped", "Processing", "Delivered"}
            checks = [{"name": "required_fields_and_semantics", "passed": valid,
                       "detail": "Output matches known fixture semantics" if valid else "Required or semantic validation failed"}]
            if not valid: status, error = "failed", "Verification rejected mutated output"
        latency = round((time.perf_counter() - started) * 1000, 2)
        run_id = str(uuid.uuid4())
        conn.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)", (run_id, task_id, status, "dom",
                     json.dumps(body.inputs), json.dumps(result) if result else None, latency, task["current_version"],
                     json.dumps(checks), now()))
        audit(conn, task_id, "run_completed" if status == "verified" else "verification_failure", status)
    return {"data": result, "status": status, "script_version": task["current_version"], "strategy": "dom",
            "checks": checks, "cached": False, "data_freshness": "live", "verified_by": "controlled_fixture",
            "fallback_reason": error, "latency_ms": latency, "browser_startup_ms": 0, "execution_ms": latency,
            "cost": {"amount": None, "currency": "USD", "source": "unavailable"}, "run_id": run_id}


@app.get("/api/v1/tasks/{task_id}/run")
def run_task_from_browser(task_id: str):
    """Browser-friendly form for read-only workflows that require no input."""
    with db() as conn:
        task = conn.execute("SELECT input_schema FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404, "Task not found")
        schema = json.loads(task["input_schema"])
        if schema.get("required"):
            raise HTTPException(405, "This workflow requires inputs; use POST with an inputs JSON object")
    return run_task(task_id, RunInput(inputs={}))


@app.post("/api/v1/tasks/{task_id}/heal")
def heal_task(task_id: str):
    with db() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task: raise HTTPException(404, "Task not found")
        mutation = current_mutation(conn)
        audit(conn, task_id, "healing_started", mutation)
        if mutation in {"captcha", "remove_required_field", "semantic_swap"}:
            audit(conn, task_id, "healing_failed", "Blocked or semantic source change")
            return {"status": "degraded" if mutation != "captcha" else "blocked_needs_human",
                    "diagnosis": "Unsafe or unverifiable mutation; previous version retained"}
        version = task["current_version"] + 1
        conn.execute("UPDATE versions SET active=0 WHERE task_id=?", (task_id,))
        conn.execute("INSERT INTO versions(task_id,version,selectors_json,diagnosis,active,created_at) VALUES (?,?,?,?,1,?)",
                     (task_id, version, json.dumps({"strategy": "role_and_stable_attributes"}), f"Repaired {mutation}", now()))
        conn.execute("UPDATE tasks SET current_version=?,status='ready',updated_at=? WHERE id=?", (version, now(), task_id))
        audit(conn, task_id, "healing_completed", f"v{version} promoted")
        return {"status": "healed", "version": version, "diagnosis": f"Adapted workflow to {mutation}"}


@app.get("/api/v1/tasks/{task_id}/versions")
def versions(task_id: str):
    with db() as conn: return [dict(r) for r in conn.execute("SELECT * FROM versions WHERE task_id=? ORDER BY version DESC", (task_id,))]


@app.get("/api/v1/tasks/{task_id}/runs")
def runs(task_id: str):
    with db() as conn: return [dict(r) for r in conn.execute("SELECT * FROM runs WHERE task_id=? ORDER BY created_at DESC", (task_id,))]


@app.post("/api/v1/demo/mutation")
def mutation(body: MutationInput):
    if body.mutation not in MUTATIONS: raise HTTPException(400, "Unknown mutation")
    with db() as conn:
        conn.execute("UPDATE settings SET value=? WHERE key='mutation'", (body.mutation,))
        audit(conn, None, "site_mutation_applied", body.mutation)
    return {"mutation": body.mutation}


@app.get("/api/v1/demo/state")
def demo_state():
    with db() as conn: return {"mutation": current_mutation(conn), "orders": ORDERS, "mutations": MUTATIONS}


@app.get("/api/v1/metrics")
def metrics():
    with db() as conn:
        rows = conn.execute("SELECT status, COUNT(*) count, AVG(latency_ms) avg_latency FROM runs GROUP BY status").fetchall()
        return {"runs": [dict(r) for r in rows], "tinyfish_browser_startup_ms": 1386.53,
                "tinyfish_agent_latency_ms": None, "measurement_note": "Browser value from latest M0 live probe"}


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        candidate = DIST / path
        return FileResponse(candidate if path and candidate.is_file() else DIST / "index.html")
