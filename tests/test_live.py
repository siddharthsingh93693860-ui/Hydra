import os

import pytest

from hydra.probe import probe_agent, probe_browser


def live_key():
    if os.getenv("HYDRA_LIVE_TESTS") != "1":
        pytest.skip("Live TinyFish tests require HYDRA_LIVE_TESTS=1 (paid service)")
    key = os.getenv("TINYFISH_API_KEY")
    if not key:
        pytest.skip("Live TinyFish tests require TINYFISH_API_KEY")
    return key


@pytest.mark.live
def test_live_agent_stream_and_structured_output():
    result = probe_agent(live_key())
    assert result["status"] == "COMPLETED"
    assert "STARTED" in result["event_types"] and "COMPLETE" in result["event_types"]


@pytest.mark.live
def test_live_browser_cdp_actions_reuse_and_inactivity():
    result = probe_browser(live_key())
    assert result["status"] == "passed" and result["session_reuse"]
