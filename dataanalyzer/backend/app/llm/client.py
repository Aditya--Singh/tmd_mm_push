"""A small client for a model that is installed on this machine.

Only the OpenAI-compatible way of talking to a model is used, because that is what Ollama
and vLLM both offer. When no model can be reached, the caller is told so and falls back on
its own rules, so that the service works on a machine without a model as well.
"""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.llm.models import resolve as resolve_model

log = logging.getLogger("analyzer.llm")


class NoModelAvailable(RuntimeError):
    """No model could be reached, so the rules of the app are used instead."""


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.model, self.model_reason = resolve_model()
        self.last_error = ""

    @property
    def available(self) -> bool:
        return bool(self.model)

    def describe(self) -> dict:
        return {
            "model": self.model,
            "model_reason": self.model_reason,
            "base_url": self.settings.llm_base_url,
            "available": self.available,
            "last_error": self.last_error,
        }

    async def complete(self, system: str, user: str, max_tokens: int | None = None) -> str:
        """Ask the model, and get the answer as text."""
        if not self.model:
            raise NoModelAvailable(self.model_reason or "no model is available")

        settings = self.settings

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "temperature": settings.llm_temperature,
            "max_tokens": max_tokens or settings.llm_max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {settings.llm_api_key or 'ollama'}"},
                )

                response.raise_for_status()

                data = response.json()
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"[:300]
            log.warning("the model could not be reached: %s", self.last_error)

            raise NoModelAvailable(self.last_error) from exc

        try:
            return (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            self.last_error = "the model answered in a way that was not understood"

            raise NoModelAvailable(self.last_error)


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client

    if _client is None:
        _client = LLMClient()

    return _client


def reset_llm() -> None:
    """Forget the client, so that a change in the settings is noticed."""
    global _client

    _client = None
