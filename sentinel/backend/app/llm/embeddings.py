"""Embedding back-ends.

* fastembed      - local ONNX model (default BAAI/bge-small-en-v1.5, 384-d). No GPU, no API key, runs on ARM64 (GB10).
* openai_compat  - an embeddings endpoint such as Ollama (`nomic-embed-text`, `bge-m3`) or vLLM.
* hash           - deterministic feature hashing. Zero dependencies; used automatically if the others fail so the
                   pipeline never stops. Retrieval quality is lower, which the UI reports.
"""
from __future__ import annotations

import asyncio
import logging
import time
import re
import zlib

import numpy as np

from app.config import get_settings

log = logging.getLogger("sentinel.embeddings")
_TOKEN = re.compile(r"[a-z0-9]+(?:[./-][a-z0-9]+)*")


def _normalize(m: np.ndarray) -> np.ndarray:
    m = m.astype(np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


class HashEmbedder:
    def __init__(self, dim: int = 768) -> None:
        self.dim = dim
        self.name = f"hash-{dim}"

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        toks = _TOKEN.findall(text.lower())
        grams = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
        for g in grams:
            h = zlib.crc32(g.encode())
            v[h % self.dim] += 1.0 if (h >> 31) & 1 else -1.0
        return v

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return _normalize(np.stack([self._vec(t) for t in texts])) if texts else np.zeros((0, self.dim), np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


class FastEmbedEmbedder:
    def __init__(self, model: str) -> None:
        from fastembed import TextEmbedding

        cache = get_settings().data_dir / "models"
        cache.mkdir(parents=True, exist_ok=True)
        self._model = TextEmbedding(model_name=model, cache_dir=str(cache))
        self.name = f"fastembed:{model}"
        self.dim = len(next(iter(self._model.embed(["dimension probe"]))))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), np.float32)
        return _normalize(np.array(list(self._model.passage_embed(texts, batch_size=32))))

    def embed_query(self, text: str) -> np.ndarray:
        return _normalize(np.array(list(self._model.query_embed([text]))))[0]


class OpenAICompatEmbedder:
    def __init__(self, model: str, base_url: str, api_key: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(base_url=base_url, api_key=api_key or "none", timeout=120)
        self._model = model
        self.name = f"openai_compat:{model}"
        self.dim = len(self._client.embeddings.create(model=model, input=["dimension probe"]).data[0].embedding)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), np.float32)
        out = []
        for i in range(0, len(texts), 64):
            resp = self._client.embeddings.create(model=self._model, input=texts[i : i + 64])
            out.extend(d.embedding for d in resp.data)
        return _normalize(np.array(out))

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


class Embedder:
    """Thread-offloading facade with automatic fallback."""

    def __init__(self) -> None:
        s = get_settings()
        self.fallback_reason: str | None = None
        provider = s.embedding_provider.lower()
        try:
            if provider == "fastembed":
                self._impl = FastEmbedEmbedder(s.embedding_model)
            elif provider == "openai_compat":
                # after a reboot the app can start before Ollama; give the embedding server a minute to come up
                last: Exception | None = None
                for attempt in range(12):
                    try:
                        self._impl = OpenAICompatEmbedder(s.embedding_model, s.embedding_base_url or s.llm_base_url, s.llm_api_key)
                        break
                    except Exception as exc:  # noqa: PERF203
                        last = exc
                        if "model" in str(exc).lower() and "not found" in str(exc).lower():
                            break  # model not pulled: waiting will not help
                        log.info("embedding server not ready, retrying", extra={"attempt": attempt + 1})
                        time.sleep(5)
                else:
                    raise last  # type: ignore[misc]
                if not hasattr(self, "_impl"):
                    raise last  # type: ignore[misc]
            else:
                self._impl = HashEmbedder()
        except Exception as exc:  # model download blocked, server down, package missing...
            self.fallback_reason = f"{provider} unavailable ({type(exc).__name__}: {exc})"[:300]
            log.warning("embedding provider fallback to hashing: %s", self.fallback_reason)
            self._impl = HashEmbedder()

    @property
    def name(self) -> str:
        return self._impl.name

    @property
    def dim(self) -> int:
        return self._impl.dim

    async def embed_documents(self, texts: list[str]) -> np.ndarray:
        return await asyncio.to_thread(self._impl.embed_documents, texts)

    async def embed_query(self, text: str) -> np.ndarray:
        return await asyncio.to_thread(self._impl.embed_query, text)


class Reranker:
    """Optional cross-encoder reranking (fastembed TextCrossEncoder)."""

    def __init__(self) -> None:
        s = get_settings()
        self.enabled = False
        self.name = None
        if not s.reranker_enabled:
            return
        try:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._model = TextCrossEncoder(model_name=s.reranker_model, cache_dir=str(s.data_dir / "models"))
            self.enabled = True
            self.name = s.reranker_model
        except Exception as exc:
            log.warning("reranker disabled: %s", exc)

    async def rerank(self, query: str, docs: list[str]) -> list[float]:
        return await asyncio.to_thread(lambda: list(self._model.rerank(query, docs)))


_embedder: Embedder | None = None
_reranker: Reranker | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker
