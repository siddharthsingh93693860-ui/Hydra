"""Documented TinyFish REST contracts; transport injection keeps tests offline."""
import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

AGENT_URL = "https://agent.tinyfish.ai/v1/automation/run-sse"
BROWSER_URL = "https://api.browser.tinyfish.ai"


class ProviderError(RuntimeError):
    def __init__(self, code, status=None, retry_after=None):
        self.code, self.status, self.retry_after = code, status, retry_after
        # Do not include response bodies, credentials, or CDP connection URLs.
        super().__init__(f"TinyFish error: {code}; HTTP {status}")


def check_response(response):
    if response.is_error:
        try:
            code = response.json().get("error", {}).get("code", "HTTP_ERROR")
        except (ValueError, AttributeError):
            code = "HTTP_ERROR"
        raise ProviderError(code, response.status_code, response.headers.get("retry-after"))


def sse_events(lines):
    """Parse SSE frames, including comments, multiline data and a trailing frame."""
    data = []
    for line in lines:
        if not line:
            if data:
                yield json.loads("\n".join(data))
                data = []
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        yield json.loads("\n".join(data))


@dataclass
class AgentEvidence:
    start_url: str
    goal: str
    output_schema: dict | None
    run_id: str | None = None
    events: list[dict] = field(default_factory=list)
    output: Any = None
    duration_ms: float = 0
    usage: Any = None
    streaming_url: str | None = None
    status: str = "RUNNING"
    error: str | None = None


class TinyFishAgentClient:
    def __init__(self, api_key, transport=None):
        if not api_key:
            raise ProviderError("MISSING_API_KEY")
        self.client = httpx.Client(headers={"X-API-Key": api_key}, transport=transport,
                                   timeout=httpx.Timeout(330, connect=60))

    def close(self):
        self.client.close()

    def run(self, url, goal, output_schema=None, max_steps=20, max_seconds=300):
        evidence = AgentEvidence(url, goal, output_schema)
        started = time.perf_counter()
        payload = {"url": url, "goal": goal,
                   "browser_profile": "lite", "use_vault": False, "use_profile": False,
                   "agent_config": {"max_steps": max_steps, "max_duration_seconds": max_seconds}}
        if output_schema is not None:
            payload["output_schema"] = output_schema
        try:
            with self.client.stream("POST", AGENT_URL, json=payload) as response:
                if response.is_error:
                    response.read()
                check_response(response)
                for event in sse_events(response.iter_lines()):
                    evidence.events.append(event)
                    evidence.run_id = event.get("run_id", evidence.run_id)
                    evidence.streaming_url = event.get("streaming_url", evidence.streaming_url)
                    evidence.usage = event.get("usage", evidence.usage)
                    if event.get("type") == "COMPLETE":
                        evidence.status = event.get("status", "FAILED")
                        evidence.output = event.get("result")
                        if evidence.status != "COMPLETED":
                            evidence.error = "AGENT_FAILED"
                        break
                    if event.get("type") in ("FAILED", "ERROR"):
                        evidence.status, evidence.error = "FAILED", "AGENT_FAILED"
                        break
                else:
                    evidence.status, evidence.error = "FAILED", "INCOMPLETE_STREAM"
        except (httpx.HTTPError, ProviderError, ValueError) as exc:
            evidence.status = "FAILED"
            evidence.error = exc.code if isinstance(exc, ProviderError) else type(exc).__name__
        finally:
            evidence.duration_ms = (time.perf_counter() - started) * 1000
        return evidence


class TinyFishSessions:
    def __init__(self, api_key, transport=None):
        if not api_key:
            raise ProviderError("MISSING_API_KEY")
        self.client = httpx.Client(headers={"X-API-Key": api_key}, transport=transport, timeout=90)

    def create(self, timeout_seconds=300):
        started = time.perf_counter()
        response = self.client.post(BROWSER_URL, json={"timeout_seconds": timeout_seconds,
                                                      "proxy_config": {"enabled": False}})
        check_response(response)
        session = response.json()
        if not session.get("session_id") or not str(session.get("cdp_url", "")).startswith("wss://"):
            raise ProviderError("INVALID_SESSION_RESPONSE")
        return session, (time.perf_counter() - started) * 1000

    def delete(self, session_id):
        response = self.client.delete(f"{BROWSER_URL}/{quote(session_id, safe='')}")
        check_response(response)
        if response.status_code != 204:
            raise ProviderError("TERMINATION_UNCONFIRMED", response.status_code)

    def close(self):
        self.client.close()
