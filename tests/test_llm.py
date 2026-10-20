import json

import httpx
import pytest

from hydra.llm import LLMError, OpenAICompatibleLLM


def test_openai_compatible_llm_contract():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer test-only"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["temperature"] == 0.1
        return httpx.Response(200, json={"model":"served-model","choices":[{"message":{"content":"ok"}}],
                                         "usage":{"total_tokens":5}})
    client = OpenAICompatibleLLM("test-only", "https://llm.invalid/v1", "test-model", httpx.MockTransport(handler))
    try:
        result = client.complete("system", "user")
        assert result.content == "ok" and result.usage == {"total_tokens":5}
    finally:
        client.close()


def test_llm_error_does_not_leak_provider_message():
    client = OpenAICompatibleLLM("test-only", "https://llm.invalid/v1", "test-model",
        httpx.MockTransport(lambda req: httpx.Response(401, json={"error":{"code":"invalid_api_key","message":"secret"}})))
    try:
        with pytest.raises(LLMError, match="invalid_api_key") as caught:
            client.complete("system", "user")
        assert "secret" not in str(caught.value)
    finally:
        client.close()
