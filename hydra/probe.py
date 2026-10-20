"""Run with python -m hydra.probe; requires an explicit live opt-in."""
import json
import os
import time
from pathlib import Path

from hydra.browser import TinyFishBrowserProvider
from hydra.tinyfish import TinyFishAgentClient

SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}
FIXTURE = """<label for='order'>Order ID</label><input id='order'>
<button id='search' onclick="document.querySelector('#result').textContent=document.querySelector('#order').value">Search</button>
<div id='result'></div>"""


def probe_agent(key):
    from jsonschema import validate
    client = TinyFishAgentClient(key)
    try:
        evidence = client.run("https://example.com", "Read the page heading and return it as title. Do not log in or bypass any access block.", SCHEMA)
        if evidence.status == "COMPLETED":
            validate(evidence.output, SCHEMA)
        # Persist only controlled public output; raw progress can contain sensitive content.
        return {"status": evidence.status, "run_id": evidence.run_id,
                "start_url": evidence.start_url, "goal": evidence.goal, "output_schema": SCHEMA,
                "event_types": [e.get("type") for e in evidence.events],
                "output": evidence.output, "duration_ms": evidence.duration_ms,
                "usage": evidence.usage, "error": evidence.error,
                "streaming_url_available": bool(evidence.streaming_url)}
    finally:
        client.close()


def probe_browser(key):
    provider = TinyFishBrowserProvider(key, timeout_seconds=5)
    report = {}
    try:
        provider.open_session()
        report.update(provider.get_session_metrics())
        provider.goto("https://example.com")
        # Owned in-memory fixture tests controls without submitting to a third-party site.
        provider.evaluate("() => { document.body.innerHTML = " + json.dumps(FIXTURE) + "; }")
        started = time.perf_counter()
        for value in ("ORD-1024", "ORD-1025"):
            provider.fill("#order", value)
            provider.press("#order", "Tab")
            provider.click("#search")
            provider.wait("#result")
            assert provider.extract({"order_id": "#result"}) == {"order_id": value}
        report.update(status="passed", session_reuse=True,
                      execution_ms=(time.perf_counter() - started) * 1000)
        report["snapshot"] = provider.snapshot()
        # Disconnect before idling: Playwright can otherwise issue background CDP commands.
        cdp_url = provider.session["cdp_url"]
        provider.playwright.stop()
        provider.playwright = None
        time.sleep(8)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.connect_over_cdp(cdp_url, timeout=10000)
                report["inactivity_observation"] = "still_connectable_after_8_seconds"
                browser.close()
            except Exception as exc:
                report["inactivity_observation"] = "reconnect_failed_after_8_seconds"
                report["inactivity_error_type"] = type(exc).__name__
        return report
    finally:
        try:
            provider.close_session()
        finally:
            provider.sessions.close()


def main():
    from dotenv import load_dotenv
    load_dotenv()
    key = os.getenv("TINYFISH_API_KEY")
    report = {"milestone": "M0", "agent": {}, "browser": {}}
    if not key or os.getenv("HYDRA_LIVE_TESTS") != "1":
        reason = "Missing TINYFISH_API_KEY" if not key else "Set HYDRA_LIVE_TESTS=1 to enable paid live probes"
        for name in ("agent", "browser"):
            report[name] = {"status": "blocked", "reason": reason}
    else:
        for name, operation in (("agent", probe_agent), ("browser", probe_browser)):
            try:
                report[name] = operation(key)
            except Exception as exc:
                report[name] = {"status": "failed", "error_type": type(exc).__name__}
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/m0.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["agent"].get("status") == "COMPLETED" and report["browser"].get("status") == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
