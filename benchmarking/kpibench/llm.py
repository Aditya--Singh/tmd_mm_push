"""Local LLM client (Ollama or any OpenAI-compatible server such as vLLM).

Data never leaves the machine: remote endpoints are refused unless ALLOW_REMOTE_LLM=true.
Every call is recorded (purpose, model, prompt version, latency, sizes) for observability and
model-risk governance. If no LLM is reachable the app keeps working in deterministic template mode.

Which model is used
-------------------
`OLLAMA_MODEL` names the model to use. It may also be `auto`, which means the best model that
is actually installed on the server is used. A model that is named but not pulled is replaced
by the best one that is there, unless `OLLAMA_STRICT_MODEL=true` says otherwise, and the
reason is always reported so that it can be shown in the interface.
"""

from __future__ import annotations

import hashlib
import json
import re
import time

import httpx

from .config import settings
from .observability import log, record_llm_call
from .security import is_local_url, redact_pii

PROMPTS: dict[str, str] = {}  # purpose -> template (filled by modules); version = sha1 prefix


#: The families of model this app prefers, best first. A machine usually holds one or two
#: families, and the newest one of them is usually the one that was meant.
PREFERRED_FAMILIES: tuple[str, ...] = (
    "qwen3",
    "qwen2.5",
    "qwen2",
    "llama3.3",
    "llama3.2",
    "llama3.1",
    "llama3",
    "mistral-nemo",
    "mistral",
    "gemma3",
    "gemma2",
    "phi4",
    "command-r",
    "deepseek-r1",
)

#: Words that mark a model as one for embeddings rather than one for text.
EMBEDDING_WORDS: tuple[str, ...] = (
    "embed",
    "bge",
    "gte-",
    "e5-",
    "minilm",
    "mxbai",
)


def prompt_version(template: str) -> str:
    return "p-" + hashlib.sha1(template.encode()).hexdigest()[:10]


def model_family(name: str) -> str:
    """The family of a model: `qwen3:8b` belongs to `qwen3`."""
    return str(name or "").split(":")[0].strip().lower()


def model_size_b(name: str) -> float:
    """The size of a model in billions of parameters, as far as the name says."""
    tag = str(name or "").split(":")[1] if ":" in str(name or "") else ""

    match = re.search(r"(\d+(?:\.\d+)?)\s*b\b", tag)

    if not match:
        return 0.0

    try:
        return float(match.group(1))
    except ValueError:
        return 0.0


def is_embedding_model(name: str) -> bool:
    """Whether a model is one for embeddings rather than one for text."""
    lowered = str(name or "").lower()

    return any(word in lowered for word in EMBEDDING_WORDS)


def score_model(name: str) -> float:
    """
    How good a model is, in the order this app prefers.

    The family comes first: the newest family that is installed is the one that was meant.
    Within a family the larger model wins.
    """
    family = model_family(name)

    rank = (
        PREFERRED_FAMILIES.index(family)
        if family in PREFERRED_FAMILIES
        else len(PREFERRED_FAMILIES)
    )

    size = min(model_size_b(name), 999.0)

    # A named tag is better than the rolling `:latest` of the same model.
    specific = 0.0 if str(name).endswith(":latest") else 5.0

    return (len(PREFERRED_FAMILIES) - rank) * 10000.0 + size * 10.0 + specific


def pick_best_model(names: list[str]) -> str | None:
    """The best model of those installed on the server, or None if there is none."""
    candidates = [
        name
        for name in (names or [])
        if name and not is_embedding_model(name)
    ]

    if not candidates:
        return None

    return max(candidates, key=score_model)


class LLM:
    def __init__(self) -> None:
        self.provider = settings.LLM_PROVIDER.lower()
        self._status_cache: tuple[float, dict] | None = None
        self._resolved_model: str | None = None

    @property
    def model(self) -> str:
        if self.provider != "ollama":
            return settings.OPENAI_COMPAT_MODEL

        if self._resolved_model:
            return self._resolved_model

        return (settings.OLLAMA_MODEL or "").strip() or "auto"

    def _base(self) -> str:
        return settings.OLLAMA_URL if self.provider == "ollama" else settings.OPENAI_COMPAT_URL

    def _pulled(self) -> list[str] | None:
        """The models the server has, or None if it cannot be reached."""
        try:
            response = httpx.get(f"{settings.OLLAMA_URL}/api/tags", timeout=4)
            response.raise_for_status()

            return [m["name"] for m in response.json().get("models", [])]
        except Exception:
            return None

    @staticmethod
    def _match(names: list[str], wanted: str) -> str | None:
        """Whether the server holds this model, and under which name."""
        if wanted in names:
            return wanted

        if f"{wanted}:latest" in names:
            return f"{wanted}:latest"

        if ":" in wanted:
            # A particular tag was asked for; only that tag will do.
            return None

        matches = [name for name in names if name.split(":")[0] == wanted]

        return matches[0] if matches else None

    def resolve(self, names: list[str]) -> tuple[str | None, str]:
        """
        Which model to use, and why.

        The model named in the settings wins whenever it is installed. When it is not, the best
        model that is installed is used instead, and the reason says so.
        """
        configured = (settings.OLLAMA_MODEL or "").strip()

        if configured and configured.lower() != "auto":
            matched = self._match(names, configured)

            if matched:
                return matched, f"the model named in OLLAMA_MODEL ({configured})"

            if settings.OLLAMA_STRICT_MODEL:
                return None, (
                    f"'{configured}' is not pulled. Run: ollama pull {configured}"
                )

            best = pick_best_model(names)

            if best:
                return best, (
                    f"'{configured}' is not pulled, so '{best}' is used instead. "
                    f"Run: ollama pull {configured}"
                )

            return None, (
                f"'{configured}' is not pulled and no other model is installed. "
                f"Run: ollama pull {configured}"
            )

        best = pick_best_model(names)

        if best:
            return best, f"the best model on this server ({best})"

        return None, "no model is installed. Run: ollama pull qwen3:8b"

    def status(self, force: bool = False) -> dict:
        if self._status_cache and not force and time.time() - self._status_cache[0] < 30:
            return self._status_cache[1]
        st = {"provider": self.provider, "model": self.model, "available": False, "models": [], "reason": ""}
        if self.provider == "none":
            st["reason"] = "LLM disabled (template mode)"
        elif not settings.ALLOW_REMOTE_LLM and not is_local_url(self._base()):
            st["reason"] = "Refused: LLM endpoint is not local and ALLOW_REMOTE_LLM is false"
        else:
            try:
                if self.provider == "ollama":
                    names = self._pulled()

                    if names is None:
                        st["reason"] = (
                            "LLM server not reachable. Start it with: ollama serve"
                        )
                    else:
                        st["models"] = names

                        resolved, reason = self.resolve(names)

                        if resolved:
                            self._resolved_model = resolved

                            st["model"] = resolved
                            st["available"] = True
                            st["reason"] = reason
                        else:
                            st["available"] = False
                            st["reason"] = reason

                        st["embed_available"] = any(
                            n.split(":")[0] == settings.EMBED_MODEL.split(":")[0]
                            for n in names
                        )
                else:
                    r = httpx.get(f"{settings.OPENAI_COMPAT_URL}/models", timeout=4)
                    st["models"] = [m["id"] for m in r.json().get("data", [])]
                    st["available"] = bool(st["models"])
                    st["embed_available"] = False
            except Exception as exc:
                st["reason"] = f"LLM server not reachable ({type(exc).__name__}). Start it with: ollama serve"
        self._status_cache = (time.time(), st)
        return st

    @property
    def available(self) -> bool:
        return bool(self.status().get("available"))

    def chat(self, system: str, user: str, purpose: str, template: str | None = None, json_mode: bool = False,
             temperature: float = 0.1, max_tokens: int = 900) -> str | None:
        if not self.available:
            return None
        user, pii = redact_pii(user)
        if pii:
            log.warning("PII redacted before LLM call (%s): %s", purpose, ",".join(pii))
        pv = prompt_version(template or system)
        t0 = time.perf_counter()
        text, err, ptok, ctok = None, None, None, None
        try:
            if self.provider == "ollama":
                body = {"model": self.model, "stream": False,
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                        "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 8192}}
                if json_mode:
                    body["format"] = "json"
                r = httpx.post(f"{settings.OLLAMA_URL}/api/chat", json=body, timeout=settings.LLM_TIMEOUT)
                r.raise_for_status()
                d = r.json()
                text = d.get("message", {}).get("content", "")
                ptok, ctok = d.get("prompt_eval_count"), d.get("eval_count")
            else:
                body = {"model": self.model, "temperature": temperature, "max_tokens": max_tokens,
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
                if json_mode:
                    body["response_format"] = {"type": "json_object"}
                r = httpx.post(f"{settings.OPENAI_COMPAT_URL}/chat/completions", json=body, timeout=settings.LLM_TIMEOUT)
                r.raise_for_status()
                d = r.json()
                text = d["choices"][0]["message"]["content"]
                u = d.get("usage") or {}
                ptok, ctok = u.get("prompt_tokens"), u.get("completion_tokens")
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            log.warning("LLM call failed (%s): %s", purpose, err)
        lat = int((time.perf_counter() - t0) * 1000)
        record_llm_call(purpose=purpose, provider=self.provider, model=self.model, prompt_version=pv,
                        prompt_chars=len(system) + len(user), completion_chars=len(text or ""),
                        prompt_tokens=ptok, completion_tokens=ctok, latency_ms=lat, ok=err is None, error=err)
        return text

    def chat_json(self, system: str, user: str, purpose: str, template: str | None = None) -> dict | None:
        raw = self.chat(system, user, purpose, template=template, json_mode=True, temperature=0.0)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", raw, re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    return None
        return None

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        st = self.status()
        if self.provider != "ollama" or not st.get("embed_available"):
            return None
        try:
            r = httpx.post(f"{settings.OLLAMA_URL}/api/embed", json={"model": settings.EMBED_MODEL, "input": texts},
                           timeout=settings.LLM_TIMEOUT)
            r.raise_for_status()
            return r.json().get("embeddings")
        except Exception as exc:
            log.warning("Embedding call failed: %s", exc)
            return None


llm = LLM()
