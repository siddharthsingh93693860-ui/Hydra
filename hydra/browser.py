"""M0 browser adapters. Trusted probes only; no untrusted script execution."""
import time
from copy import deepcopy
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

from hydra.tinyfish import TinyFishSessions, ProviderError


@runtime_checkable
class BrowserProvider(Protocol):
    def open_session(self): ...
    def close_session(self): ...
    def goto(self, url: str): ...
    def snapshot(self): ...
    def screenshot(self): ...
    def click(self, selector: str): ...
    def fill(self, selector: str, value: str): ...
    def press(self, selector: str, key: str): ...
    def wait(self, selector: str): ...
    def extract(self, selectors: dict): ...
    def evaluate(self, expression: str): ...
    def capture_network_events(self): ...
    def get_session_metrics(self): ...


class PlaywrightOperations:
    def _page(self):
        if not self.browser or not self.browser.is_connected() or self.page.is_closed():
            raise ProviderError("INACTIVE_SESSION")
        return self.page

    def goto(self, url):
        if urlsplit(url).scheme not in ("http", "https"):
            raise ValueError("HTTP/HTTPS required")
        self._page().goto(url, wait_until="domcontentloaded")

    def snapshot(self):
        # Metadata only: intentionally no form values or arbitrary page text in M0.
        dom = self._page().locator("button,input,select,a,[role]").evaluate_all("""els => els.slice(0,200).map(e => ({
          tag: e.tagName.toLowerCase(), role: e.getAttribute('role'),
          type: e.getAttribute('type'), disabled: !!e.disabled}))""")
        return {"elements": dom, "accessibility": {"roles": [e["role"] for e in dom if e["role"]]},
                "limitation": "Metadata-only M0 snapshot; accessible names deferred pending redaction"}

    def screenshot(self):
        return self._page().screenshot(mask=[self.page.locator("input,textarea,[contenteditable]")])

    def click(self, selector): self._page().click(selector)
    def fill(self, selector, value): self._page().fill(selector, value)
    def press(self, selector, key): self._page().press(selector, key)
    def wait(self, selector): self._page().wait_for_selector(selector)
    def extract(self, selectors):
        return {name: self._page().locator(selector).inner_text() for name, selector in selectors.items()}
    def evaluate(self, expression): return self._page().evaluate(expression)

    def capture_network_events(self):
        # No headers, cookies, request bodies, URLs or response bodies retained.
        return deepcopy(self.network)

    def get_session_metrics(self):
        return {"browser_startup_ms": self.startup_ms, "cdp_connect_ms": self.connect_ms,
                "session_connected": bool(self.browser and self.browser.is_connected())}

    def _attach(self):
        context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
        self.page = context.pages[0] if context.pages else context.new_page()
        self.page.set_default_timeout(15000)
        self.page.wait_for_load_state("domcontentloaded")
        self.network = []
        self.page.on("response", lambda r: self.network.append({"status": r.status,
                                                              "method": r.request.method}))


class TinyFishBrowserProvider(PlaywrightOperations):
    def __init__(self, api_key, transport=None, timeout_seconds=300):
        self.sessions = TinyFishSessions(api_key, transport)
        self.timeout_seconds = timeout_seconds
        self.browser = self.playwright = self.session = None

    def open_session(self):
        from playwright.sync_api import sync_playwright
        if self.session:
            raise ProviderError("SESSION_ALREADY_OPEN")
        self.session, self.startup_ms = self.sessions.create(self.timeout_seconds)
        try:
            self.playwright = sync_playwright().start()
            started = time.perf_counter()
            self.browser = self.playwright.chromium.connect_over_cdp(self.session["cdp_url"])
            self.connect_ms = (time.perf_counter() - started) * 1000
            self._attach()
        except Exception:
            self.close_session()
            raise

    def close_session(self):
        try:
            if self.session:
                self.sessions.delete(self.session["session_id"])
                self.session = None
        finally:
            if self.playwright:
                self.playwright.stop()
                self.playwright = None
            self.browser = None
        # Keep HTTP client usable if a failed DELETE needs to be retried.


class LocalPlaywrightProvider(PlaywrightOperations):
    def __init__(self):
        self.browser = self.playwright = None

    def open_session(self):
        from playwright.sync_api import sync_playwright
        if self.browser:
            raise ProviderError("SESSION_ALREADY_OPEN")
        started = time.perf_counter()
        self.playwright = sync_playwright().start()
        try:
            self.browser = self.playwright.chromium.launch()
            self.startup_ms, self.connect_ms = (time.perf_counter() - started) * 1000, 0
            self._attach()
        except Exception:
            self.close_session()
            raise

    def close_session(self):
        try:
            if self.browser: self.browser.close()
        finally:
            if self.playwright: self.playwright.stop()
            self.browser = self.playwright = None


class MockBrowserProvider:
    """Scripted contract mock, never represented as a browser or TinyFish run."""
    def __init__(self, expected_calls):
        self.expected = list(expected_calls)
        self.active = False

    def _call(self, name, *args):
        if not self.active and name != "open_session":
            raise ProviderError("INACTIVE_SESSION")
        if not self.expected:
            raise AssertionError(f"Unexpected call {name}")
        expected_name, expected_args, result = self.expected.pop(0)
        assert (name, args) == (expected_name, expected_args)
        if isinstance(result, Exception): raise result
        return deepcopy(result)

    def open_session(self):
        result = self._call("open_session")
        self.active = True
        return result
    def close_session(self):
        result = self._call("close_session")
        self.active = False
        return result
    def goto(self, url): return self._call("goto", url)
    def snapshot(self): return self._call("snapshot")
    def screenshot(self): return self._call("screenshot")
    def click(self, selector): return self._call("click", selector)
    def fill(self, selector, value): return self._call("fill", selector, value)
    def press(self, selector, key): return self._call("press", selector, key)
    def wait(self, selector): return self._call("wait", selector)
    def extract(self, selectors): return self._call("extract", selectors)
    def evaluate(self, expression): return self._call("evaluate", expression)
    def capture_network_events(self): return self._call("capture_network_events")
    def get_session_metrics(self): return self._call("get_session_metrics")
