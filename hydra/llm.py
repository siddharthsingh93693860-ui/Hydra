"""Small OpenAI-compatible LLM adapter used by the guided compiler."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    content: str
    model: str
    usage: dict[str, Any] | None


class OpenAICompatibleLLM:
    def __init__(self, api_key: str, base_url: str, model: str, transport=None):
        if not api_key or not base_url or not model:
            raise LLMError("LLM_API_KEY, LLM_BASE_URL and HYDRA_MODEL are required")
        self.model = model
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
            transport=transport,
        )

    @classmethod
    def from_env(cls):
        return cls(
            os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY", ""),
            os.getenv("LLM_BASE_URL"),
            os.getenv("HYDRA_MODEL", ""),
        )

    def complete(self, system: str, user: str) -> LLMResult:
        response = self.client.post("/chat/completions", json={
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.1,
        })
        if response.is_error:
            try:
                code = response.json().get("error", {}).get("code", "LLM_HTTP_ERROR")
            except (ValueError, AttributeError):
                code = "LLM_HTTP_ERROR"
            raise LLMError(f"LLM request failed: {code}; HTTP {response.status_code}")
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM returned an invalid response shape") from exc
        return LLMResult(content=content, model=data.get("model", self.model), usage=data.get("usage"))

    def close(self):
        self.client.close()
