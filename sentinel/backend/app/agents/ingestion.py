"""Watcher, Ingestion and Summarizer agents.

Watcher    polls the RBI RSS feeds and returns items not yet in the database.
Ingestion  turns each item into clean text + metadata (RBI ref no., department, addressees, PDF link), chunks it with
           contextual headers, embeds the chunks and stores everything.
Summarizer produces a structured, bank-oriented brief (key points, action items, applicability, priority). Rules run
           first; the LLM refines them. Which one decided each field is recorded so a reviewer can see it.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin

import feedparser
import httpx
import numpy as np
from bs4 import BeautifulSoup

from app.config import get_settings
from app.core.db import session_scope
from app.core.models import Chunk, Circular, utcnow
from app.agents.rbi_pages import financial_year
from app.core.utils import as_utc
from app.llm.embeddings import get_embedder
from app.llm.provider import get_llm
from app.observability.tracer import tracer
from app.rag import text as T

log = logging.getLogger("sentinel.ingestion")
IST = timezone(timedelta(hours=5, minutes=30))
_ID_RE = re.compile(r"(?:[?&](?:id|prid)=)(\d+)", re.I)


@dataclass
class FeedItem:
    source: str
    guid: str
    title: str
    link: str
    description_html: str
    published_at: datetime | None
    pdf_url: str | None = None
    listing_group: str | None = None
    update_of: int | None = None  # id of the stored circular this item revises (title changed on RBI's page)


PAGE_SOURCES = ("master_circular", "master_direction")


def mark_superseded() -> int:
    """Each Master Circular is reissued every year. Mark all but the newest version of each subject as superseded."""
    from app.agents.rbi_pages import subject_key

    with session_scope() as db:
        rows = db.query(Circular).filter(Circular.source == "master_circular").all()
        groups: dict[str, list[Circular]] = {}
        for c in rows:
            groups.setdefault(subject_key(c.title), []).append(c)
        changed = 0
        for items in groups.values():
            items.sort(key=lambda c: (as_utc(c.published_at) or datetime.min.replace(tzinfo=timezone.utc), c.id), reverse=True)
            newest = items[0]
            for c in items:
                want = None if c is newest else newest.id
                if c.superseded_by != want:
                    c.superseded_by = want
                    changed += 1
        return changed


def _http() -> httpx.AsyncClient:
    s = get_settings()
    return httpx.AsyncClient(
        headers={"User-Agent": s.http_user_agent, "Accept": "*/*", "Accept-Language": "en-IN,en;q=0.9"},
        timeout=s.http_timeout_seconds,
        verify=s.http_verify_ssl,
        follow_redirects=True,
    )


def make_guid(source: str, link: str) -> str:
    m = _ID_RE.search(link or "")
    return f"{source}:{m.group(1)}" if m else f"{source}:{(link or '').strip().lower()}"


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:  # RBI publishes Indian Standard Time without an offset
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(timezone.utc)


async def _fetch_bytes(client: httpx.AsyncClient, url: str) -> bytes:
    if url.startswith("file://") or not url.startswith("http"):
        path = Path(url.removeprefix("file://"))
        if not path.exists():
            # saved copies of RBI pages (tests) use Windows-safe names: "...aspx?id=1" is stored as "...aspx_id_1.html"
            path = path.with_name(re.sub(r"[?=&]", "_", path.name) + ".html")
        return await asyncio.to_thread(path.read_bytes)
    resp = await client.get(url)
    resp.raise_for_status()
    return resp.content


# ----------------------------------------------------------------- Watcher
async def watch_feeds() -> tuple[list[FeedItem], list[dict]]:
    """Read every RBI source. Return (new or revised items, per-source report)."""
    from app.agents.rbi_pages import fetch_listing

    s = get_settings()
    items: list[FeedItem] = []
    report: list[dict] = []
    async with _http() as client:
        for source, url in s.feeds:
            async with tracer.span("Watcher", f"fetch {source} feed", input={"url": url}) as sp:
                try:
                    raw = await _fetch_bytes(client, url)
                    parsed = feedparser.parse(raw)
                    entries = parsed.entries or []
                    for e in entries:
                        link = (e.get("link") or "").strip()
                        items.append(
                            FeedItem(
                                source=source,
                                guid=make_guid(source, link),
                                title=re.sub(r"\s+", " ", e.get("title", "")).strip(),
                                link=link,
                                description_html=e.get("summary") or e.get("description") or "",
                                published_at=_parse_date(e.get("published")),
                            )
                        )
                    sp.output = {"entries": len(entries), "bozo": bool(parsed.get("bozo")) and not entries}
                    report.append({"source": source, "url": url, "entries": len(entries), "ok": True})
                except Exception as exc:
                    sp.status = "error"
                    sp.output = {"error": str(exc)}
                    report.append({"source": source, "url": url, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
                    log.warning("feed fetch failed", extra={"feed": url, "error": str(exc)})

        for source, url in s.page_sources:
            async with tracer.span("Watcher", f"read {source.replace('_', ' ')} listing", input={"url": url}) as sp:
                try:
                    rows, info = await fetch_listing(client, source, url, s.mc_years_limit, _fetch_bytes)
                    for r in rows:
                        items.append(
                            FeedItem(
                                source=source,
                                guid=r["guid"],
                                title=r["title"],
                                link=r["link"],
                                description_html="",
                                published_at=r["published_at"],
                                pdf_url=r["pdf_url"],
                                listing_group=r["listing_group"],
                            )
                        )
                    sp.output = info
                    ok = info["entries"] > 0
                    if not ok:
                        sp.status = "error"
                    report.append({"source": source, "url": url, "entries": info["entries"], "ok": ok,
                                   **({} if ok else {"error": "page loaded but no entries could be read - the layout may have changed"})})
                except Exception as exc:
                    sp.status = "error"
                    sp.output = {"error": str(exc)}
                    report.append({"source": source, "url": url, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
                    log.warning("listing fetch failed", extra={"page": url, "error": str(exc)})

    async with tracer.span("Watcher", "detect new and revised items", input={"candidates": len(items)}) as sp:
        guids = [i.guid for i in items]
        with session_scope() as db:
            known = {g: (cid, t) for g, cid, t in db.query(Circular.guid, Circular.id, Circular.title).filter(Circular.guid.in_(guids)).all()} if guids else {}
        seen: set[str] = set()
        out: list[FeedItem] = []
        revised = []
        for it in items:
            if it.guid in seen:
                continue
            seen.add(it.guid)
            if it.guid not in known:
                out.append(it)
            elif it.source in PAGE_SOURCES and _norm(known[it.guid][1]) != _norm(it.title):
                # RBI keeps the same id and changes the title, e.g. "(Updated as on November 10, 2026)"
                it.update_of = known[it.guid][0]
                out.append(it)
                revised.append({"id": it.update_of, "old": known[it.guid][1][:120], "new": it.title[:120]})
        sp.output = {
            "new": sum(1 for i in out if not i.update_of),
            "revised": revised[:20],
            "already_known": len(known) - len(revised),
            "titles": [i.title for i in out][:20],
        }
    return out, report


def _norm(title: str) -> str:
    return re.sub(r"\W+", " ", (title or "").lower()).strip()


# --------------------------------------------------------------- Ingestion
def _main_content(soup: BeautifulSoup):
    """The element holding the circular text on an RBI detail page."""
    for sel in ("table.td", "div#doublescroll", "div.content", "main"):
        el = soup.select_one(sel)
        if el and len(el.get_text(" ", strip=True)) > 200:
            return el
    for bad in soup(["script", "style", "nav", "header", "footer"]):
        bad.decompose()
    best, best_score = None, 0
    for el in soup.find_all(["td", "div"]):
        score = len(el.find_all("p", recursive=True))
        if el.find(["td", "div"], recursive=False) and score == best_score:
            continue
        if score > best_score:
            best, best_score = el, score
    return best


async def _detail_page(client: httpx.AsyncClient, url: str) -> tuple[str | None, str | None]:
    """Return (main_text, pdf_url) from an RBI notification / press release / master circular / direction page."""
    try:
        html = (await _fetch_bytes(client, url)).decode("utf-8", errors="replace")
    except Exception as exc:
        log.info("detail page unavailable", extra={"url": url, "error": str(exc)})
        return None, None
    soup = BeautifulSoup(html, "lxml")
    pdf_url = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().split("?")[0].endswith(".pdf"):
            pdf_url = urljoin(url, href).replace("http://rbidocs", "https://rbidocs")
            break
    main = _main_content(soup)
    text = T.html_to_text(str(main)) if main else None
    return text, pdf_url


async def ingest_item(item: FeedItem) -> int | None:
    """Ingest (or re-ingest a revised) item. Returns circular id."""
    s = get_settings()
    verb = "re-ingest revised" if item.update_of else "ingest"
    async with tracer.span("Ingestion", f"{verb}: {item.title[:60]}", input={"guid": item.guid, "url": item.link, "source": item.source}) as sp:
        text = T.html_to_text(item.description_html)
        pdf_url = item.pdf_url
        used = "rss_description"
        if (s.fetch_detail_page or not text.strip()) and item.link:
            async with _http() as client:
                await asyncio.sleep(s.polite_delay_seconds)
                page_text, page_pdf = await _detail_page(client, item.link)
                pdf_url = pdf_url or page_pdf
                if page_text and len(page_text.split()) > len(text.split()) * 1.2:
                    text, used = page_text, "detail_page"
                if len(text.split()) < 150 and pdf_url:
                    try:
                        pdf_text = T.pdf_to_text(await _fetch_bytes(client, pdf_url))
                        if len(pdf_text.split()) > len(text.split()):
                            text, used = pdf_text, "pdf"
                    except Exception as exc:
                        log.info("pdf extraction failed", extra={"pdf": pdf_url, "error": str(exc)})
        if not text.strip():
            text = item.title
            used = "title_only"

        meta = T.extract_metadata(text)
        published = item.published_at or (meta.issued_on.replace(tzinfo=IST).astimezone(timezone.utc) if meta.issued_on else None)
        applic, _ = T.applicability_heuristic(item.title, meta.addressees, item.source, item.listing_group)
        priority, _ = T.priority_heuristic(item.title, text, item.source, applic, revised=bool(item.update_of))

        header = T.contextual_header(item.title, meta.rbi_ref, meta.issued_on or published, item.source, item.listing_group)
        pieces = T.chunk_text(text, s.chunk_size_words, s.chunk_overlap_words)
        emb = get_embedder()
        vectors = await emb.embed_documents([f"{header}\n{p}" for p in pieces])

        fields = dict(
            guid=item.guid,
            source=item.source,
            title=item.title,
            url=item.link,
            pdf_url=pdf_url,
            published_at=published,
            rbi_ref=meta.rbi_ref,
            dept_ref=meta.dept_ref,
            department=meta.department or item.listing_group,
            listing_group=item.listing_group,
            addressees=meta.addressees,
            signatory=meta.signatory,
            raw_html=item.description_html[:500_000],
            text=text,
            content_hash=hashlib.sha256(text.encode()).hexdigest(),
            priority=priority,
            applicability=applic,
            tags=T.tag_heuristic(item.title, text),
            status="indexed",
            chunk_count=len(pieces),
            ingest_trace_id=sp.trace_id,
        )
        with session_scope() as db:
            if item.update_of:
                circ = db.get(Circular, item.update_of)
                db.query(Chunk).filter(Chunk.circular_id == circ.id).delete()
                for k, v in fields.items():
                    setattr(circ, k, v)
                circ.revision = (circ.revision or 0) + 1
                circ.updated_at = utcnow()
                circ.summary = None
                circ.notified_at = None
            else:
                circ = Circular(**fields)
                db.add(circ)
            db.flush()
            for i, (piece, vec) in enumerate(zip(pieces, vectors)):
                db.add(
                    Chunk(
                        circular_id=circ.id,
                        ordinal=i,
                        header=header,
                        text=piece,
                        word_count=len(piece.split()),
                        embedding=np.asarray(vec, dtype=np.float32).tobytes(),
                        embedding_model=emb.name,
                    )
                )
            cid = circ.id
        sp.output = {
            "circular_id": cid,
            "revision": bool(item.update_of),
            "text_source": used,
            "words": len(text.split()),
            "chunks": len(pieces),
            "embedding_model": emb.name,
            "rbi_ref": meta.rbi_ref,
            "dept_ref": meta.dept_ref,
            "listing_group": item.listing_group,
            "applicability": applic,
            "pdf_url": pdf_url,
        }
        if used == "title_only":
            sp.set(warning="no text could be extracted; only the title is searchable")
        log.info("circular ingested", extra={"circular_id": cid, "chunks": len(pieces), "title": item.title[:80], "source": item.source})
        return cid


async def reembed_stale(chunk_ids: list[int]) -> int:
    """Re-embed chunks produced by a different embedding model (e.g. after switching providers)."""
    if not chunk_ids:
        return 0
    emb = get_embedder()
    async with tracer.span("Indexer", "re-embed stale chunks", input={"count": len(chunk_ids)}) as sp:
        done = 0
        for i in range(0, len(chunk_ids), 128):
            batch = chunk_ids[i : i + 128]
            with session_scope() as db:
                rows = db.query(Chunk).filter(Chunk.id.in_(batch)).all()
                payload = [(r.id, f"{r.header}\n{r.text}") for r in rows]
            vecs = await emb.embed_documents([p for _, p in payload])
            with session_scope() as db:
                for (cid, _), v in zip(payload, vecs):
                    row = db.get(Chunk, cid)
                    row.embedding = np.asarray(v, dtype=np.float32).tobytes()
                    row.embedding_model = emb.name
            done += len(payload)
        sp.output = {"re_embedded": done, "model": emb.name}
        return done


# -------------------------------------------------------------- Summarizer
SUMMARY_SYSTEM = """You are the Summarizer agent in a regulatory-intelligence system used by compliance and business
officers of a large Indian public sector (scheduled commercial) bank. You read one Reserve Bank of India circular,
notification, press release, Master Circular or Master Direction and produce a precise brief. Master Circulars and
Master Directions consolidate earlier instructions on a subject: summarise the scope, the key requirements and what
changed if the text says so.

Rules:
- Use only the document text. Never invent dates, numbers, reference numbers or obligations.
- Write in formal, plain banking English. No marketing language.
- "applicability" is from the point of view of a scheduled commercial bank in the public sector.
- "action_items" are concrete things the bank must do; return [] if the document is informational.
- Priority: High = immediate compliance / financial / AML impact; Medium = regulatory change with a lead time;
  Low = informational.

Return one JSON object with exactly these keys:
{"headline": str (<= 20 words), "summary": str (2-4 sentences), "key_points": [str, ...] (3-6 items),
 "action_items": [str, ...], "effective_date": str or null, "deadline": str or null,
 "applicability": {"verdict": "Applicable" | "Not applicable" | "Review" | "Informational" | "For comments",
                   "reason": str},
 "priority": "High" | "Medium" | "Low", "priority_reason": str,
 "tags": [str, ...] (<= 5), "impacted_functions": [str, ...] (e.g. Compliance, Treasury, Credit, Operations, IT)}"""

_ACTION_RE = re.compile(r"\b(advised to|are required to|shall ensure|should ensure|must|are directed|may bring|shall be|are requested)\b", re.I)
_EFFECT_RE = re.compile(
    rf"(with immediate effect|come into (?:force|effect)(?: from| on)?\s+(?:{T.MONTHS})\s+\d{{1,2}},\s*\d{{4}})", re.I
)


def _extractive_summary(c: Circular) -> dict:
    paras = [p.strip() for p in re.split(r"\n\s*\n", c.text) if len(p.split()) > 12]
    body = [p for p in paras if not T.RBI_REF_RE.search(p) and not T.SALUTATION_RE.match(p)]
    summary = " ".join(body[:2])[:700]
    key_points = []
    for p in body[1:]:
        first = re.split(r"(?<=[.;])\s", p, maxsplit=1)[0]
        if 8 < len(first.split()) < 60:
            key_points.append(first)
        if len(key_points) >= 5:
            break
    actions = []
    for p in body:
        for sent in re.split(r"(?<=[.])\s+", p):
            if _ACTION_RE.search(sent) and 6 < len(sent.split()) < 70:
                actions.append(sent.strip())
            if len(actions) >= 4:
                break
    eff = _EFFECT_RE.search(c.text)
    verdict, reason = T.applicability_heuristic(c.title, c.addressees, c.source, c.listing_group)
    prio, prio_reason = T.priority_heuristic(c.title, c.text, c.source, verdict, revised=bool(c.revision))
    return {
        "headline": c.title[:160],
        "summary": summary or c.title,
        "key_points": key_points,
        "action_items": actions,
        "effective_date": eff.group(0) if eff else None,
        "deadline": None,
        "applicability": {"verdict": verdict, "reason": reason},
        "priority": prio,
        "priority_reason": prio_reason,
        "tags": T.tag_heuristic(c.title, c.text),
        "impacted_functions": [],
        "generated_by": "rules (extractive)",
    }


def _doc_for_llm(c: Circular, limit: int = 14000) -> str:
    text = c.text
    if len(text) > limit:
        text = text[: limit - 2500] + "\n\n[... middle of document omitted for length ...]\n\n" + text[-2500:]
    meta = f"Title: {c.title}\nType: {c.source.replace('_', ' ')}\nRBI listing heading: {c.listing_group or '-'}\n"
    meta += f"RBI ref: {c.rbi_ref or '-'}\nDept ref: {c.dept_ref or '-'}\n"
    meta += f"Addressees: {c.addressees or '-'}\nURL: {c.url}\n"
    return f"{meta}\n--- DOCUMENT TEXT ---\n{text}"


async def summarize_circular(circular_id: int, use_llm: bool = True) -> dict:
    with session_scope() as db:
        c = db.get(Circular, circular_id)
        if c is None:
            raise ValueError(f"circular {circular_id} not found")
        db.expunge(c)
    async with tracer.span("Summarizer", f"summarize: {c.title[:60]}", input={"circular_id": circular_id}) as sp:
        base = _extractive_summary(c)
        result = base
        llm = get_llm()
        if llm.available and use_llm:
            try:
                data, res = await llm.complete_json(
                    SUMMARY_SYSTEM, [{"role": "user", "content": _doc_for_llm(c)}], max_tokens=1200, span_name="summarize"
                )
                if data and data.get("summary"):
                    result = {**base, **{k: v for k, v in data.items() if v not in (None, "", [])}}
                    if not isinstance(result.get("applicability"), dict):
                        result["applicability"] = base["applicability"]
                    if result.get("priority") not in ("High", "Medium", "Low"):
                        result["priority"] = base["priority"]
                    result["generated_by"] = f"llm ({res.model}) + rules"
                    result["rules_view"] = {"priority": base["priority"], "applicability": base["applicability"]}
                    # Explicit evidence (the title or addressee list names the entity type) beats the model's reading.
                    rule_ap = base["applicability"]
                    if rule_ap["reason"].startswith(T.STRONG_REASONS) and result["applicability"].get("verdict") != rule_ap["verdict"]:
                        result["model_view"] = {"applicability": result["applicability"], "priority": result.get("priority")}
                        result["applicability"] = {**rule_ap, "reason": rule_ap["reason"] + " (rule kept over the model's view)"}
                        if rule_ap["verdict"] == "Not applicable":
                            result["priority"] = "Low"
                            result["priority_reason"] = "Not addressed to commercial banks."
                        sp.set(applicability_override=True)
            except Exception as exc:
                sp.set(llm_error=str(exc)[:300])
                log.warning("LLM summary failed, using extractive summary", extra={"error": str(exc)[:200]})
        with session_scope() as db:
            row = db.get(Circular, circular_id)
            row.summary = result
            row.summary_model = result.get("generated_by")
            row.priority = result.get("priority", row.priority)
            row.applicability = (result.get("applicability") or {}).get("verdict", row.applicability)
            row.tags = result.get("tags") or row.tags
            if row.status in ("new", "indexed"):
                row.status = "summarized"
        sp.output = {
            "priority": result.get("priority"),
            "applicability": result.get("applicability"),
            "generated_by": result.get("generated_by"),
        }
        return result


def circular_brief(c: Circular) -> dict:
    """Serialisable view used by the API and e-mails."""
    return {
        "id": c.id,
        "title": c.title,
        "source": c.source,
        "url": c.url,
        "pdf_url": c.pdf_url,
        "published_at": as_utc(c.published_at).isoformat() if c.published_at else None,
        "rbi_ref": c.rbi_ref,
        "dept_ref": c.dept_ref,
        "department": c.department,
        "addressees": c.addressees,
        "priority": c.priority,
        "applicability": c.applicability,
        "tags": c.tags or [],
        "status": c.status,
        "summary": c.summary,
        "chunk_count": c.chunk_count,
        "notified_at": as_utc(c.notified_at).isoformat() if c.notified_at else None,
        "ingest_trace_id": c.ingest_trace_id,
        "listing_group": c.listing_group,
        "financial_year": financial_year(as_utc(c.published_at)),
        "superseded_by": c.superseded_by,
        "ai_summary": bool(c.summary_model and c.summary_model.startswith("llm")),
        "revision": c.revision or 0,
        "updated_at": as_utc(c.updated_at).isoformat() if c.updated_at else None,
    }
