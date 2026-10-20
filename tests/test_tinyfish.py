import json

import httpx
import pytest

from hydra.browser import BrowserProvider, MockBrowserProvider, TinyFishBrowserProvider, LocalPlaywrightProvider
from hydra.tinyfish import TinyFishAgentClient, TinyFishSessions, ProviderError, sse_events


def stream_transport(events):
    body = "\n\n".join("data: " + json.dumps(e) for e in events)
    return httpx.MockTransport(lambda request: httpx.Response(200, text=body))


def test_sse_multiline_comments_and_trailing_frame():
    assert list(sse_events([": heartbeat", "event: message", 'data: {"type":',
                            'data: "STARTED"}', "", 'data: {"type":"COMPLETE"}'])) == [
                                {"type": "STARTED"}, {"type": "COMPLETE"}]


def test_agent_contract_and_evidence():
    def handler(request):
        assert str(request.url).endswith("/v1/automation/run-sse")
        assert request.headers["X-API-Key"] == "test-only"
        payload = json.loads(request.content)
        assert payload["output_schema"] == {"type": "object"}
        assert payload["agent_config"]["max_steps"] == 20
        assert payload["use_vault"] is False
        events = [{"type": "STARTED", "run_id": "mock-1"},
                  {"type": "PROGRESS", "purpose": "Read heading"},
                  {"type": "COMPLETE", "status": "COMPLETED", "result": {"title": "Example"},
                   "usage": {"credits": 1}}]
        return httpx.Response(200, text="\n\n".join("data: " + json.dumps(e) for e in events))
    client = TinyFishAgentClient("test-only", httpx.MockTransport(handler))
    try:
        result = client.run("https://example.com", "Read heading", {"type": "object"})
        assert result.status == "COMPLETED"
        assert result.output == {"title": "Example"}
        assert result.events[1]["purpose"] == "Read heading"
        assert result.run_id == "mock-1" and result.usage == {"credits": 1}
        assert result.duration_ms >= 0
    finally:
        client.close()


@pytest.mark.parametrize("events,error", [
    ([{"type": "STARTED"}], "INCOMPLETE_STREAM"),
    ([{"type": "COMPLETE", "status": "FAILED", "result": None}], "AGENT_FAILED"),
    ([{"type": "ERROR"}], "AGENT_FAILED"),
])
def test_agent_never_promotes_failed_or_partial_stream(events, error):
    client = TinyFishAgentClient("test-only", stream_transport(events))
    try:
        result = client.run("https://example.com", "Read", {})
        assert result.status == "FAILED" and result.error == error
        assert result.usage is None
    finally:
        client.close()


@pytest.mark.parametrize("status,code", [(401, "INVALID_API_KEY"), (402, "INSUFFICIENT_CREDITS"),
                                         (429, "RATE_LIMIT_EXCEEDED"), (503, "SERVICE_BUSY")])
def test_browser_provider_errors_are_not_success_and_preserve_retry_after(status, code):
    transport = httpx.MockTransport(lambda req: httpx.Response(status, headers={"Retry-After": "12"},
                                  json={"error": {"code": code, "message": "SECRET"}}))
    sessions = TinyFishSessions("test-only", transport)
    try:
        with pytest.raises(ProviderError) as caught:
            sessions.create()
        assert caught.value.code == code and caught.value.retry_after == "12"
        assert "SECRET" not in str(caught.value)
    finally:
        sessions.close()


def test_browser_create_uses_cdp_contract_and_explicit_delete():
    calls = []
    def handler(request):
        calls.append(request.method)
        assert request.headers["X-API-Key"] == "test-only"
        if request.method == "POST":
            assert json.loads(request.content)["proxy_config"] == {"enabled": False}
            return httpx.Response(201, json={"session_id": "mock-session", "cdp_url": "wss://mock/cdp",
                                           "base_url": "https://mock/polling"})
        assert str(request.url).endswith("/mock-session")
        return httpx.Response(204)
    sessions = TinyFishSessions("test-only", httpx.MockTransport(handler))
    try:
        session, startup = sessions.create()
        assert session["cdp_url"] != session["base_url"]
        assert startup >= 0
        sessions.delete(session["session_id"])
        assert calls == ["POST", "DELETE"]
    finally:
        sessions.close()


def test_missing_cdp_url_is_rejected():
    sessions = TinyFishSessions("test-only", httpx.MockTransport(lambda req:
        httpx.Response(201, json={"session_id": "mock", "base_url": "https://polling"})))
    try:
        with pytest.raises(ProviderError, match="INVALID_SESSION_RESPONSE"):
            sessions.create()
    finally:
        sessions.close()


def test_mock_strict_sequence_and_inactive_session():
    provider = MockBrowserProvider([
        ("open_session", (), None), ("fill", ("#order", "ORD-1024"), None),
        ("extract", ({"status": "#status"},), {"status": "Shipped"}), ("close_session", (), None)])
    assert isinstance(provider, BrowserProvider)
    with pytest.raises(ProviderError, match="INACTIVE_SESSION"):
        provider.fill("#order", "ORD-1024")
    provider.open_session()
    provider.fill("#order", "ORD-1024")
    assert provider.extract({"status": "#status"}) == {"status": "Shipped"}
    provider.close_session()
    assert not provider.expected


def test_concrete_providers_conform_without_opening_browsers():
    remote = TinyFishBrowserProvider("test-only")
    try:
        assert isinstance(remote, BrowserProvider)
        assert isinstance(LocalPlaywrightProvider(), BrowserProvider)
    finally:
        remote.sessions.close()


def test_delete_failure_retains_session_for_retry():
    remote = TinyFishBrowserProvider("test-only", httpx.MockTransport(lambda req:
        httpx.Response(503, json={"error": {"code": "SERVICE_BUSY"}})))
    remote.session = {"session_id": "mock"}
    try:
        with pytest.raises(ProviderError): remote.close_session()
        assert remote.session["session_id"] == "mock"
    finally:
        remote.sessions.close()


def test_agent_http_error_is_evidence_not_success():
    client = TinyFishAgentClient("test-only", httpx.MockTransport(lambda req:
        httpx.Response(429, json={"error": {"code": "RATE_LIMIT_EXCEEDED"}})))
    try:
        result = client.run("https://example.com", "Read", {})
        assert result.status == "FAILED" and result.error == "RATE_LIMIT_EXCEEDED"
    finally:
        client.close()


def test_missing_credentials_fail_before_network():
    with pytest.raises(ProviderError, match="MISSING_API_KEY"): TinyFishAgentClient("")
    with pytest.raises(ProviderError, match="MISSING_API_KEY"): TinyFishSessions("")


def test_cdp_wiring_and_cleanup_with_fake_playwright(monkeypatch):
    import sys
    from types import SimpleNamespace
    from unittest.mock import Mock

    page = Mock()
    browser = Mock(contexts=[SimpleNamespace(pages=[page])])
    runtime = Mock()
    runtime.chromium.connect_over_cdp.return_value = browser
    module = SimpleNamespace(sync_playwright=lambda: SimpleNamespace(start=lambda: runtime))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    requests = []
    def handler(request):
        requests.append(request.method)
        if request.method == "DELETE": return httpx.Response(204)
        return httpx.Response(201, json={"session_id": "mock", "cdp_url": "wss://mock/cdp",
                                       "base_url": "https://must-not-connect"})
    provider = TinyFishBrowserProvider("test-only", httpx.MockTransport(handler))
    try:
        provider.open_session()
        runtime.chromium.connect_over_cdp.assert_called_once_with("wss://mock/cdp")
        page.wait_for_load_state.assert_called_once_with("domcontentloaded")
        provider.close_session()
        assert requests == ["POST", "DELETE"]
        runtime.stop.assert_called_once()
    finally:
        provider.sessions.close()


def test_cdp_failure_releases_remote_session(monkeypatch):
    import sys
    from types import SimpleNamespace
    from unittest.mock import Mock

    runtime = Mock()
    runtime.chromium.connect_over_cdp.side_effect = RuntimeError("simulated CDP failure")
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(
        sync_playwright=lambda: SimpleNamespace(start=lambda: runtime)))
    requests = []
    def handler(request):
        requests.append(request.method)
        return httpx.Response(204) if request.method == "DELETE" else httpx.Response(201, json={
            "session_id": "mock", "cdp_url": "wss://mock/cdp"})
    provider = TinyFishBrowserProvider("test-only", httpx.MockTransport(handler))
    try:
        with pytest.raises(RuntimeError, match="simulated CDP failure"):
            provider.open_session()
        assert requests == ["POST", "DELETE"]
        assert provider.session is None
        runtime.stop.assert_called_once()
    finally:
        provider.sessions.close()
