"""Model-agnostic LLM client.

Supported back-ends
  * openai_compat - any OpenAI-compatible endpoint: Ollama / vLLM on the GB10, OpenAI, Azure OpenAI, a Bedrock gateway
  * anthropic     - Claude via the Anthropic API
  * none          - no model; agents fall back to deterministic, extractive behaviour so the app still works end to end

Every call is wrapped in an "LLM" span that records provider, model, latency and token usage.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import AsyncIterator

from app.config import get_settings
from app.core.utils import estimate_tokens, extract_json
from app.llm.models import resolve as resolve_model
from app.observability.tracer import tracer

log = logging.getLogger("sentinel.llm")


@dataclass
class LLMResult:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: float


class LLMUnavailable(RuntimeError):
    pass


class LLMClient:
    def __init__(self) -> None:
        self.s = get_settings()
        self.provider = self.s.llm_provider.lower().strip()
        self._client = None
        self.model_reason = ""
        if self.provider == "openai_compat":
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                base_url=self.s.llm_base_url, api_key=self.s.llm_api_key or "none", timeout=self.s.llm_timeout_seconds
            )
            self.model, self.model_reason = resolve_model()
            if not self.model:
                log.warning("no model for writing is available; the agents will use their own fallbacks")
                self.provider = "none"
        elif self.provider == "anthropic":
            from anthropic import AsyncAnthropic

            if not self.s.anthropic_api_key:
                log.warning("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty; running without an LLM")
                self.provider = "none"
            else:
                self._client = AsyncAnthropic(api_key=self.s.anthropic_api_key, timeout=self.s.llm_timeout_seconds)
            self.model = self.s.anthropic_model
            self.model_reason = "named in the settings"
        else:
            self.provider = "none"
            self.model = "none"
            self.model_reason = "no model is configured"
        self._json_mode_supported = True
        self._usage_stream_supported = True
        self._healthy: bool | None = None
        self._last_error: str | None = None

    # ------------------------------------------------------------------ info
    @property
    def available(self) -> bool:
        # agents always try the model when one is configured and fall back on failure
        return self.provider != "none"

    def describe(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "model_reason": self.model_reason,
            "base_url": self.s.llm_base_url if self.provider == "openai_compat" else None,
            "healthy": self._healthy,
            "last_error": self._last_error,
        }

    def _mark(self, ok: bool, err: str | None = None) -> None:
        # health is informational (shown in the UI); it never blocks a retry
        self._healthy = ok
        self._last_error = err

    async def health_check(self) -> dict:
        if self.provider == "none":
            return self.describe()
        try:
            await self.complete("Reply with the single word OK.", [{"role": "user", "content": "ping"}], max_tokens=200, span_name="health_check")
        except Exception:
            pass
        return self.describe()

    # ------------------------------------------------------------- complete
    async def complete(
        self,
        system: str,
        messages: list[dict],
        *,
        json_mode: bool = False,
        max_tokens: int | None = None,
        temperature: float | None = None,
        span_name: str = "chat.completion",
    ) -> LLMResult:
        if self.provider == "none":
            raise LLMUnavailable("No LLM configured")
        max_tokens = max_tokens or self.s.llm_max_tokens
        temperature = self.s.llm_temperature if temperature is None else temperature
        async with tracer.span(
            "LLM",
            span_name,
            input={"system": system, "messages": messages, "json_mode": json_mode},
            attributes={"gen_ai.system": self.provider, "gen_ai.request.model": self.model, "gen_ai.request.temperature": temperature},
        ) as sp:
            t0 = time.perf_counter()
            try:
                if self.provider == "anthropic":
                    text, tin, tout = await self._anthropic_complete(system, messages, max_tokens, temperature, json_mode)
                else:
                    text, tin, tout = await self._openai_complete(system, messages, max_tokens, temperature, json_mode)
            except Exception as exc:
                self._mark(False, f"{type(exc).__name__}: {exc}"[:300])
                raise
            self._mark(True)
            latency = (time.perf_counter() - t0) * 1000
            sp.add_usage(self.model, tin, tout, self.provider)
            sp.output = {"text": text}
            return LLMResult(text=text, model=self.model, tokens_in=tin, tokens_out=tout, latency_ms=latency)

    async def complete_json(self, system: str, messages: list[dict], **kw) -> tuple[dict | None, LLMResult]:
        res = await self.complete(system, messages, json_mode=True, **kw)
        return extract_json(res.text), res

    async def _openai_complete(self, system, messages, max_tokens, temperature, json_mode):
        msgs = [{"role": "system", "content": system}, *messages]
        kwargs = dict(model=self.model, messages=msgs, max_tokens=max_tokens, temperature=temperature)
        if json_mode and self._json_mode_supported:
            try:
                resp = await self._client.chat.completions.create(**kwargs, response_format={"type": "json_object"})
            except Exception as exc:  # some servers reject response_format
                if "response_format" not in str(exc) and "json" not in str(exc).lower():
                    raise
                self._json_mode_supported = False
                resp = await self._client.chat.completions.create(**kwargs)
        else:
            resp = await self._client.chat.completions.create(**kwargs)
        text = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        tin = getattr(usage, "prompt_tokens", None) or estimate_tokens(system + str(messages))
        tout = getattr(usage, "completion_tokens", None) or estimate_tokens(text)
        return text, tin, tout

    async def _anthropic_complete(self, system, messages, max_tokens, temperature, json_mode):
        if json_mode:
            system = system + "\n\nRespond with a single valid JSON object and nothing else."
        resp = await self._client.messages.create(
            model=self.model, system=system, messages=messages, max_tokens=max_tokens, temperature=temperature
        )
        text = "".join(getattr(b, "text", "") for b in resp.content).strip()
        return text, resp.usage.input_tokens, resp.usage.output_tokens

    # --------------------------------------------------------------- stream
    async def stream(
        self, system: str, messages: list[dict], *, max_tokens: int | None = None, span_name: str = "chat.stream"
    ) -> AsyncIterator[str]:
        if self.provider == "none":
            raise LLMUnavailable("No LLM configured")
        max_tokens = max_tokens or self.s.llm_max_tokens
        async with tracer.span(
            "LLM",
            span_name,
            input={"system": system, "messages": messages},
            attributes={"gen_ai.system": self.provider, "gen_ai.request.model": self.model, "streaming": True},
        ) as sp:
            parts: list[str] = []
            usage = {"in": 0, "out": 0}
            t0 = time.perf_counter()
            first_token_ms = None
            try:
                if self.provider == "anthropic":
                    gen = self._anthropic_stream(system, messages, max_tokens, usage)
                else:
                    gen = self._openai_stream(system, messages, max_tokens, usage)
                async for delta in gen:
                    if first_token_ms is None:
                        first_token_ms = round((time.perf_counter() - t0) * 1000, 1)
                    parts.append(delta)
                    yield delta
            except Exception as exc:
                self._mark(False, f"{type(exc).__name__}: {exc}"[:300])
                raise
            self._mark(True)
            text = "".join(parts)
            sp.add_usage(
                self.model,
                usage["in"] or estimate_tokens(system + str(messages)),
                usage["out"] or estimate_tokens(text),
                self.provider,
            )
            sp.set(time_to_first_token_ms=first_token_ms)
            sp.output = {"text": text}

    async def _openai_stream(self, system, messages, max_tokens, usage):
        msgs = [{"role": "system", "content": system}, *messages]
        kwargs = dict(model=self.model, messages=msgs, max_tokens=max_tokens, temperature=self.s.llm_temperature, stream=True)
        if self._usage_stream_supported:
            try:
                stream = await self._client.chat.completions.create(**kwargs, stream_options={"include_usage": True})
            except Exception as exc:
                if "stream_options" not in str(exc):
                    raise
                self._usage_stream_supported = False
                stream = await self._client.chat.completions.create(**kwargs)
        else:
            stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                usage["in"] = chunk.usage.prompt_tokens or 0
                usage["out"] = chunk.usage.completion_tokens or 0
            if chunk.choices:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content

    async def _anthropic_stream(self, system, messages, max_tokens, usage):
        async with self._client.messages.stream(
            model=self.model, system=system, messages=messages, max_tokens=max_tokens, temperature=self.s.llm_temperature
        ) as stream:
            async for text in stream.text_stream:
                yield text
            final = await stream.get_final_message()
            usage["in"] = final.usage.input_tokens
            usage["out"] = final.usage.output_tokens


_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
