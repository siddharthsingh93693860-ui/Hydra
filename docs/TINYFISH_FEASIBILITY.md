# M0 — TinyFish feasibility

Experiment date: **2026-10-12 (Asia/Calcutta)**.
Status: **BLOCKED — TINYFISH_API_KEY unavailable**. No service request was attempted without credentials. No M1–M6 work has started.

## Verified behavior

Offline only: 18 pytest cases pass. `tests/test_tinyfish.py` covers SSE framing, structured result handling, ordered progress, missing completion, provider failures, nullable usage, session response validation, explicit termination, inactive mocks, CDP argument wiring and cleanup after a simulated CDP failure. These tests use HTTP/Playwright doubles, not TinyFish service access.

`python -m hydra.probe` produced `artifacts/m0.json` with both integrations marked blocked due to missing credentials. The probe intentionally exits nonzero. Normal pytest reports the two live cases skipped rather than failed.

## Current official documentation

Read on the experiment date:

- [Browser reference](https://docs.tinyfish.ai/browser-api/reference): REST creation, `cdp_url`, separate `base_url`, async startup navigation, inactivity configuration and direct connections without a proxy. The implementation creates a blank session, connects, then explicitly navigates and waits.
- [Session termination](https://docs.tinyfish.ai/api-reference/terminate-a-browser-session): explicit DELETE is available; disconnecting Playwright alone is not treated as confirmed termination.
- [Agent SSE](https://docs.tinyfish.ai/api-reference/automation/run-browser-automation-with-sse-streaming): structured output schema and event messages are documented; the client checks the terminal status and rejects truncated streams.
- [Get run](https://docs.tinyfish.ai/api-reference/runs/get-run-by-id): optional step action descriptions, screenshots, HTML and video are documented. These are not evidence of a complete reusable selector trace. Retrieval of these optional artifacts is deferred pending privacy controls.

Documentation review verifies the advertised contract, **not live behavior**. Third-party examples were not used as authoritative contracts.

## Experiment coverage

| Requirement | Implementation / evidence | Current outcome |
|---|---|---|
| Natural-language Agent task | `hydra.probe.probe_agent` | BLOCKED live |
| Streaming events | `TinyFishAgentClient`, SSE unit tests | Mock verified; live BLOCKED |
| Structured result | Schema validation in Agent probe | Mock verified; live BLOCKED |
| Browser session creation | `TinyFishSessions.create` | Mock verified; live BLOCKED |
| CDP compatibility | `TinyFishBrowserProvider.open_session` | Argument wiring verified with fake Playwright only |
| goto/click/fill/press/wait/evaluate/extract | Owned form in `probe_browser` | UNVERIFIED real browser |
| Browser startup latency | Separate REST creation/CDP timers | No live measurements |
| Agent latency | Agent evidence timer | No live measurements |
| Reuse across calls | Two order values in same session | UNVERIFIED |
| Inactivity | Disconnect, wait 8s for requested 5s timeout, reconnect | UNVERIFIED; failed reconnect alone cannot prove expiration |
| Rate/concurrency errors | 429/503 fixtures preserve Retry-After; no automatic POST retry | Offline handling verified; real limits UNVERIFIED |
| Trace availability | Official run endpoint reviewed | Contract documented; live payload UNVERIFIED |
| Usage/cost | Optional `usage` captured if present; otherwise null | No reported or estimated costs |

## Measured results

| Measurement | Result |
|---|---|
| Agent execution latency | Not measured |
| Browser session creation latency | Not measured |
| CDP connection latency | Not measured |
| Deterministic workflow latency | Not measured |
| Provider usage/cost | Unavailable |
| Speed/cost advantage | No claim; no comparison data |

Test-double timing is deliberately not used as a provider benchmark.

## Provider limitations and design changes

Use CDP URL only for Playwright; the polling base URL is a different endpoint. Separate startup from execution. A successful session response does not prove a page has loaded. Explicit cleanup replaces older assumptions that sessions can only expire. Failed DELETE is surfaced and the session ID is retained in memory for retry. No automatic session-creation retry avoids accidentally duplicating billable sessions after ambiguous failures.

The compiler must inspect pages independently rather than assume Agent progress yields selectors. Accessible names and comprehensive DOM redaction are deferred: M0 snapshots expose only element tag/role/type/disabled metadata. They are not yet sufficient compiler observations. Optional artifacts and streaming URLs stay in memory; persistent evidence currently omits free-text progress to avoid claiming comprehensive redaction.

Full rate-limit scheduling, retry policies, bounded total transport deadlines, usage endpoint reconciliation, provider event-size limits and remote cancellation on client interruption remain pending. Agent server-side step/duration bounds are sent; the HTTP timeout is an inactivity timeout, not a complete worker deadline.

## Resume procedure

1. Configure `TINYFISH_API_KEY` and `HYDRA_LIVE_TESTS=1` in ignored `.env`.
2. Install project dependencies; run `python -m hydra.probe`.
3. Review real output and failures, rerun live pytest with credentials in process environment, and update this document with actual measurements.
4. Confirm Agent and Browser service access and CDP execution before starting M1. Later supply `ANTHROPIC_API_KEY`, `HYDRA_MODEL` and a publicly reachable controlled supplier site.

Do not treat a successful mocked run, a skipped test, or this document as completion of live feasibility.
