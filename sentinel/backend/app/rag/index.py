"""Hybrid retrieval: dense vectors + BM25 fused with Reciprocal Rank Fusion, optional cross-encoder rerank.

Kept in memory (rebuilt from the database after each ingestion). A few hundred thousand chunks fit comfortably in RAM
on the GB10; for larger corpora swap this class for pgvector/Qdrant behind the same `search` signature.
Each hit carries its dense rank, BM25 rank and fused score so the UI can show *why* a passage was retrieved.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
from rank_bm25 import BM25Okapi

from app.config import get_settings
from app.core.db import session_scope
from app.core.models import Chunk, Circular
from app.core.utils import as_utc
from app.llm.embeddings import get_embedder, get_reranker

log = logging.getLogger("sentinel.index")

STOP = set(
    "a an the of and or to in on for by with from at as is are be was were this that these those it its into under "
    "shall may such any all other which who whom has have had not no than then there their they them we our you your "
    "i me my also been being per vide said above below herein thereof dated".split()
)
_TOK = re.compile(r"[a-z0-9]+(?:[./-][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOK.findall(text.lower()) if t not in STOP and len(t) > 1]


@dataclass
class ChunkRecord:
    chunk_id: int
    circular_id: int
    ordinal: int
    header: str
    text: str
    title: str
    url: str
    source: str
    rbi_ref: str | None
    published_at: datetime | None
    superseded: bool = False


@dataclass
class Hit:
    record: ChunkRecord
    score: float
    dense_rank: int | None
    bm25_rank: int | None
    dense_score: float | None = None
    bm25_score: float | None = None
    rerank_score: float | None = None
    extras: dict = field(default_factory=dict)

    def to_dict(self, n: int | None = None) -> dict:
        r = self.record
        return {
            "n": n,
            "chunk_id": r.chunk_id,
            "circular_id": r.circular_id,
            "title": r.title,
            "url": r.url,
            "rbi_ref": r.rbi_ref,
            "source": r.source,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "superseded": r.superseded,
            "text": r.text,
            "score": round(self.score, 5),
            "dense_rank": self.dense_rank,
            "bm25_rank": self.bm25_rank,
            "dense_score": None if self.dense_score is None else round(self.dense_score, 4),
            "bm25_score": None if self.bm25_score is None else round(self.bm25_score, 3),
            "rerank_score": None if self.rerank_score is None else round(self.rerank_score, 4),
        }


class HybridIndex:
    def __init__(self) -> None:
        self.records: list[ChunkRecord] = []
        self.matrix: np.ndarray | None = None
        self.bm25: BM25Okapi | None = None
        self._lock = asyncio.Lock()
        self.built_at: datetime | None = None
        self.embedding_model: str | None = None

    @property
    def size(self) -> int:
        return len(self.records)

    async def rebuild(self) -> dict:
        async with self._lock:
            return await asyncio.to_thread(self._rebuild_sync)

    def _rebuild_sync(self) -> dict:
        emb = get_embedder()
        records: list[ChunkRecord] = []
        vectors: list[np.ndarray] = []
        stale: list[int] = []
        with session_scope() as db:
            rows = (
                db.query(Chunk, Circular)
                .join(Circular, Chunk.circular_id == Circular.id)
                .order_by(Chunk.id)
                .all()
            )
            for ch, circ in rows:
                if ch.embedding is None or ch.embedding_model != emb.name:
                    stale.append(ch.id)
                    continue
                vec = np.frombuffer(ch.embedding, dtype=np.float32)
                if vec.shape[0] != emb.dim:
                    stale.append(ch.id)
                    continue
                records.append(
                    ChunkRecord(
                        chunk_id=ch.id,
                        circular_id=circ.id,
                        ordinal=ch.ordinal,
                        header=ch.header,
                        text=ch.text,
                        title=circ.title,
                        url=circ.url,
                        source=circ.source,
                        rbi_ref=circ.rbi_ref,
                        published_at=as_utc(circ.published_at),
                        superseded=circ.superseded_by is not None,
                    )
                )
                vectors.append(vec)
        self.records = records
        self.matrix = np.vstack(vectors) if vectors else None
        corpus = [tokenize(f"{r.header} {r.text}") for r in records]
        self.bm25 = BM25Okapi(corpus) if corpus else None
        self.built_at = datetime.now(timezone.utc)
        self.embedding_model = emb.name
        log.info("index rebuilt", extra={"chunks": len(records), "stale_chunks": len(stale)})
        return {"chunks": len(records), "stale": stale}

    async def search(
        self,
        query: str,
        k: int | None = None,
        source: str | None = None,
        since: datetime | None = None,
        circular_ids: list[int] | None = None,
        include_superseded: bool = False,
    ) -> list[Hit]:
        s = get_settings()
        k = k or s.retrieval_top_k
        if not self.records or self.matrix is None:
            return []
        qvec = await get_embedder().embed_query(query)

        mask = np.ones(len(self.records), dtype=bool)
        for i, r in enumerate(self.records):
            if source and r.source != source:
                mask[i] = False
            elif since and (r.published_at is None or r.published_at < since):
                mask[i] = False
            elif circular_ids and r.circular_id not in circular_ids:
                mask[i] = False
            elif r.superseded and not include_superseded and not circular_ids:
                mask[i] = False  # older yearly versions of a master circular stay out unless asked for
        if not mask.any():
            return []

        dense = self.matrix @ qvec
        dense[~mask] = -np.inf
        n_cand = min(s.retrieval_candidates, int(mask.sum()))
        dense_order = np.argsort(-dense)[:n_cand]

        bm = np.array(self.bm25.get_scores(tokenize(query))) if self.bm25 else np.zeros(len(self.records))
        bm[~mask] = -np.inf
        bm_order = [i for i in np.argsort(-bm)[:n_cand] if bm[i] > 0]

        fused: dict[int, float] = {}
        d_rank = {int(i): r + 1 for r, i in enumerate(dense_order)}
        b_rank = {int(i): r + 1 for r, i in enumerate(bm_order)}
        for idx, r in d_rank.items():
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (s.rrf_k + r)
        for idx, r in b_rank.items():
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (s.rrf_k + r)

        ranked = sorted(fused.items(), key=lambda kv: -kv[1])[: max(k * 3, k)]
        hits = [
            Hit(
                record=self.records[i],
                score=score,
                dense_rank=d_rank.get(i),
                bm25_rank=b_rank.get(i),
                dense_score=float(dense[i]),
                bm25_score=float(bm[i]) if np.isfinite(bm[i]) else None,
            )
            for i, score in ranked
        ]
        rr = get_reranker()
        if rr.enabled and hits:
            scores = await rr.rerank(query, [f"{h.record.header}\n{h.record.text}" for h in hits])
            for h, sc in zip(hits, scores):
                h.rerank_score = float(sc)
            hits.sort(key=lambda h: -(h.rerank_score or 0))
        return hits[:k]


index = HybridIndex()
