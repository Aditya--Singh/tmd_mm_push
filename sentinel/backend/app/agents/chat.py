"""Conversational agent graph.

    Memory(load) -> Router -> { Retriever -> Answer -> Verifier      (qa)
                                Briefing                             (latest)
                                Resolver -> Summarizer               (summarize)
                                Resolver -> Notifier                 (email)
                                Memory(remember)                     (remember)
                                Answer                               (smalltalk) }
                 -> Memory(update)

The graph is explicit rather than a free-form tool loop: each hop is a named agent with a typed input/output, a span
in the trace, and a "step" event streamed to the UI. That is what makes every answer explainable after the fact.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from sqlalchemy import or_

from app.agents.ingestion import circular_brief, summarize_circular
from app.agents.notifier import compose_alert, compose_answer, compose_digest, send_email
from app.config import get_settings
from app.core import runtime_settings as rs
from app.core.db import session_scope
from app.core.models import Circular, Conversation, MemoryNote, Message, User, utcnow
from app.core.utils import as_utc
from app.llm.provider import get_llm
from app.observability import audit
from app.observability.tracer import tracer
from app.rag.index import index, tokenize
from app.rag.text import RBI_REF_RE

log = logging.getLogger("sentinel.chat")

INTENTS = ("qa", "latest", "summarize", "email", "remember", "smalltalk")
EMAIL_RE = re.compile(r"[^@\s<>]+@[^@\s<>]+\.[A-Za-z]{2,}")


# ======================================================================= state
@dataclass
class ChatState:
    user: dict
    conversation_id: int
    user_message: str
    user_message_id: int = 0
    summary: str = ""
    notes: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    route: dict = field(default_factory=dict)
    sources: list[dict] = field(default_factory=list)
    answer: str = ""
    verification: dict | None = None
    actions: list[dict] = field(default_factory=list)
    scope_id: int | None = None  # chat limited to one circular
    include_older: bool = False  # also search superseded yearly versions of master circulars


def _evt_step(agent: str, label: str, status: str, detail: Any = None, ms: float | None = None) -> dict:
    return {"type": "step", "agent": agent, "label": label, "status": status, "detail": detail, "ms": ms}


class Step:
    """Pairs a tracer span with UI step events."""

    def __init__(self, agent: str, label: str, input: Any = None):
        self.agent, self.label, self.input = agent, label, input
        self._cm = None
        self.span = None
        self.t0 = 0.0

    async def __aenter__(self):
        self._cm = tracer.span(self.agent, self.label, input=self.input)
        self.span = await self._cm.__aenter__()
        self.t0 = time.perf_counter()
        return self

    async def __aexit__(self, et, ev, tb):
        return await self._cm.__aexit__(et, ev, tb)

    @property
    def ms(self) -> float:
        return round((time.perf_counter() - self.t0) * 1000, 1)

    def start_event(self) -> dict:
        return _evt_step(self.agent, self.label, "running")

    def done_event(self, detail: Any = None) -> dict:
        return _evt_step(self.agent, self.label, "done", detail, self.ms)


# ====================================================================== prompts
ROUTER_SYSTEM = """You are the Router agent of "RBI Regulatory Sentinel", an assistant for officers of an Indian public
sector bank. It has an index of Reserve Bank of India notifications (circulars), press releases, Master Circulars and
Master Directions.

Classify the user's LATEST message and rewrite it as a standalone search query using the conversation context.
Intents:
- qa        : a question to be answered from the content of RBI documents
- latest    : wants to know what is new / recent / issued in a time window
- summarize : wants a summary of a specific circular (or "the latest one")
- email     : wants something e-mailed (an answer, a circular summary, or a digest)
- remember  : asks you to remember a preference or fact for future conversations
- smalltalk : greetings, thanks, or questions about the assistant itself

Return JSON only:
{"intent": one of the intents,
 "standalone_query": string,
 "circular_ref": string or null   (an RBI reference number like RBI/2026-27/302, a title fragment, or "latest"),
 "since_days": integer or null    (time window implied, e.g. today=1, this week=7, this month=30),
 "source": "notification" | "press_release" | "master_circular" | "master_direction" | null
                                  (only when the user explicitly limits the document type),
 "email_content": "answer" | "circular" | "digest" | null,
 "recipient": string or null      (an e-mail address only if the user typed one),
 "memory_note": string or null    (for remember: the fact, phrased as a note about the user),
 "reason": short string}"""

ANSWER_SYSTEM = """You are the Answer agent of "RBI Regulatory Sentinel", assisting officers of an Indian public sector
bank. Answer using ONLY the numbered RBI sources provided.

Rules:
1. Every factual sentence must end with a citation like [1] or [2][3] pointing to the sources used.
2. Quote reference numbers, dates, percentages and thresholds exactly as written in the sources.
3. If the sources do not contain the answer, say "I could not find this in the indexed RBI publications." and
   suggest how the user could refine the question. Do not use outside knowledge to fill gaps.
4. Note when a source is a draft, an amendment, or a press release rather than a binding direction.
   Master Directions and Master Circulars consolidate the instructions on a subject. When they and a later circular
   both cover the point, give the consolidated position and mention the later change, citing both.
   A source marked "superseded" is an older yearly version of a Master Circular; say so if you rely on it.
5. Be concise: a direct answer first, then supporting detail as short bullets if useful. Plain banking English."""

BRIEFING_SYSTEM = """You are the Briefing agent of "RBI Regulatory Sentinel". Given numbered summaries of recent RBI
publications, write a 3-5 sentence briefing for a bank's senior management: what changed, what needs action, and
what is merely informational. Cite each publication you mention as [n]. Use only the supplied summaries."""

MEMORY_SYSTEM = """You are the Memory agent. Update the running summary of a conversation between a bank officer and
an RBI regulatory assistant. Keep facts the assistant will need later: the user's goals, circulars discussed (with
reference numbers), decisions, and open questions. Max 120 words. Return only the updated summary text."""

SMALLTALK_SYSTEM = """You are "Regulatory Sentinel", an assistant for officers of an Indian public sector bank.
Reply briefly and warmly. If useful, mention what you can do: answer questions from indexed RBI circulars with
citations (including Master Circulars and Master Directions), list what is new, summarise a circular, e-mail answers or digests, and remember preferences."""


# =================================================================== utilities
def _heuristic_route(text: str) -> dict:
    t = text.lower().strip()
    route = {"intent": "qa", "standalone_query": text, "circular_ref": None, "since_days": None, "source": None,
             "email_content": None, "recipient": None, "memory_note": None, "reason": "rule-based router"}
    ref = RBI_REF_RE.search(text)
    if ref:
        route["circular_ref"] = ref.group(0)
    if re.search(r"\b(today)\b", t):
        route["since_days"] = 1
    elif re.search(r"\b(this|last|past) week\b|\bweekly\b", t):
        route["since_days"] = 7
    elif re.search(r"\b(this|last|past) month\b", t):
        route["since_days"] = 30
    if "press release" in t:
        route["source"] = "press_release"
    elif re.search(r"master circulars?\b", t):
        route["source"] = "master_circular"
    elif re.search(r"master directions?\b", t):
        route["source"] = "master_direction"
    m = EMAIL_RE.search(text)
    just_latest = re.search(r"\b(the )?(latest|last|most recent|newest)( one| circular| notification| press release)?[?.!]*$", t)
    if re.search(r"\b(e-?mail|mail)\b", t) and re.search(r"\b(send|email|e-mail|mail|forward)\b", t):
        route["intent"] = "email"
        route["recipient"] = m.group(0) if m else None
        if re.search(r"digest|what'?s new|today|this week|all (new|recent)", t):
            route["email_content"] = "digest"
        elif ref or re.search(r"circular|notification|press release|direction", t):
            route["email_content"] = "circular"
            route["circular_ref"] = route["circular_ref"] or ("latest" if just_latest else text)
        else:
            route["email_content"] = "answer"
    elif re.match(r"^(please )?remember\b|^note that\b|^keep in mind\b", t):
        route["intent"] = "remember"
        route["memory_note"] = re.sub(r"^(please )?(remember|note|keep in mind)( that)?\s*", "", text, flags=re.I)
    elif re.search(r"\bsummar", t):
        route["intent"] = "summarize"
        if not route["circular_ref"]:
            route["circular_ref"] = "latest" if just_latest else text
    elif re.search(r"\b(what'?s new|latest|recent|new (circulars|notifications)|issued (today|this))\b", t):
        route["intent"] = "latest"
        route["since_days"] = route["since_days"] or 7
    elif re.fullmatch(r"(hi|hello|hey|thanks|thank you|good (morning|afternoon|evening)|who are you\??|help)[!. ]*", t):
        route["intent"] = "smalltalk"
    return route


def _history_messages(state: ChatState) -> list[dict]:
    return [{"role": m["role"], "content": m["content"][:1500]} for m in state.history]


def _memory_preamble(state: ChatState) -> str:
    parts = []
    if state.summary:
        parts.append(f"Conversation memory (earlier turns): {state.summary}")
    if state.notes:
        parts.append("The user asked you to remember:\n" + "\n".join(f"- {n}" for n in state.notes))
    return "\n\n".join(parts)


def _circ_source(n: int, c: Circular) -> dict:
    sm = c.summary or {}
    return {
        "n": n,
        "circular_id": c.id,
        "chunk_id": None,
        "title": c.title,
        "url": c.url,
        "rbi_ref": c.rbi_ref,
        "source": c.source,
        "published_at": as_utc(c.published_at).isoformat() if c.published_at else None,
        "text": sm.get("summary") or c.text[:600],
        "priority": c.priority,
    }


def _summary_markdown(c: Circular, n: int | None = None) -> str:
    sm = c.summary or {}
    cite = f" [{n}]" if n else ""
    lines = [f"### {c.title}", ""]
    meta = [x for x in [c.rbi_ref, c.dept_ref, as_utc(c.published_at).strftime("%d %b %Y") if c.published_at else None] if x]
    if meta:
        lines += [f"*{' · '.join(meta)}*", ""]
    if sm.get("summary"):
        lines += [sm["summary"] + cite, ""]
    if sm.get("key_points"):
        lines += ["**Key points**"] + [f"- {p}" for p in sm["key_points"]] + [""]
    if sm.get("action_items"):
        lines += ["**Action for the bank**"] + [f"- {a}" for a in sm["action_items"]] + [""]
    ap = sm.get("applicability") or {}
    lines.append(f"**Priority:** {sm.get('priority', c.priority)} · **Applicability:** {ap.get('verdict', c.applicability)}"
                 + (f" — {ap['reason']}" if ap.get("reason") else ""))
    if sm.get("effective_date"):
        lines.append(f"**Effective:** {sm['effective_date']}")
    lines += ["", f"_Summary generated by {sm.get('generated_by', 'rules')}. Verify against the [original]({c.url})._"]
    return "\n".join(lines)


# ==================================================================== verifier
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_CITE = re.compile(r"\[(\d+)\]")
ABSTAIN = re.compile(r"could not find|not (?:found|available) in the indexed|no relevant", re.I)


def verify_answer(answer: str, sources: list[dict]) -> dict:
    """Citation and grounding check. Lexical support is a fast proxy; swap in an NLI/HHEM model for production."""
    if ABSTAIN.search(answer) and len(_CITE.findall(answer)) == 0:
        return {"verdict": "Abstained", "score": None, "detail": "Agent declined to answer beyond the sources.", "sentences": []}
    src_tokens = {s["n"]: set(tokenize(s.get("text", "") + " " + s.get("title", ""))) for s in sources}
    rows, supports, invalid, uncited = [], [], set(), 0
    for raw in _SENT_SPLIT.split(answer):
        sent = raw.strip(" -*#>")
        content = set(tokenize(_CITE.sub("", sent)))
        if len(content) < 4:
            continue
        cites = [int(c) for c in _CITE.findall(sent)]
        if not cites:
            uncited += 1
            rows.append({"sentence": sent[:240], "citations": [], "support": None})
            continue
        valid = [c for c in cites if c in src_tokens]
        invalid.update(c for c in cites if c not in src_tokens)
        pool = set().union(*(src_tokens[c] for c in valid)) if valid else set()
        support = len(content & pool) / len(content) if content else 0.0
        supports.append(support)
        rows.append({"sentence": sent[:240], "citations": cites, "support": round(support, 2)})
    cited = len(supports)
    if cited + uncited == 0:
        return {"verdict": "Not assessed", "score": None, "detail": "No factual sentences found.", "sentences": rows}
    grounding = sum(supports) / cited if cited else 0.0
    coverage = cited / (cited + uncited)
    score = round(0.7 * grounding + 0.3 * coverage, 3)
    verdict = "Grounded" if score >= 0.65 and not invalid else ("Partially grounded" if score >= 0.4 else "Weakly grounded")
    return {
        "verdict": verdict,
        "score": score,
        "grounding": round(grounding, 3),
        "citation_coverage": round(coverage, 3),
        "cited_sentences": cited,
        "uncited_sentences": uncited,
        "invalid_citations": sorted(invalid),
        "method": "lexical support of cited sources (proxy)",
        "sentences": rows[:20],
    }


# ================================================================== the graph
async def run_chat(
    user: User,
    conversation_id: int | None,
    text: str,
    ip: str | None = None,
    scope_id: int | None = None,
    include_older: bool = False,
) -> AsyncIterator[dict]:
    s = get_settings()
    llm = get_llm()
    user_info = {"id": user.id, "email": user.email, "name": user.name, "role": user.role}

    # persist the user message first so it is never lost
    with session_scope() as db:
        conv = db.get(Conversation, conversation_id) if conversation_id else None
        if conv is None or conv.user_id != user.id:
            conv = Conversation(user_id=user.id, title=(text.strip()[:60] or "New conversation"))
            db.add(conv)
            db.flush()
        um = Message(conversation_id=conv.id, role="user", content=text)
        db.add(um)
        conv.updated_at = utcnow()
        db.flush()
        state = ChatState(user=user_info, conversation_id=conv.id, user_message=text, user_message_id=um.id,
                          scope_id=scope_id, include_older=include_older)

    async with tracer.trace("chat", text[:80], actor=user.email, input={"message": text, "conversation_id": state.conversation_id}) as tr:
        audit.record(user.email, "chat.query", resource=f"conversation:{state.conversation_id}", details={"chars": len(text)}, ip=ip)
        yield {"type": "meta", "conversation_id": state.conversation_id, "user_message_id": state.user_message_id, "trace_id": tr.id}
        try:
            # ---------------------------------------------------------- memory
            async with Step("Memory", "load context") as st:
                yield st.start_event()
                with session_scope() as db:
                    conv = db.get(Conversation, state.conversation_id)
                    state.summary = conv.summary or ""
                    msgs = (
                        db.query(Message)
                        .filter(Message.conversation_id == conv.id, Message.id < state.user_message_id, Message.id > conv.summary_upto_message_id)
                        .order_by(Message.id.desc())
                        .limit(s.memory_window_messages)
                        .all()
                    )
                    state.history = [{"role": m.role, "content": m.content} for m in reversed(msgs)]
                    state.notes = [n.content for n in db.query(MemoryNote).filter(MemoryNote.user_id == user.id).order_by(MemoryNote.id).limit(20)]
                detail = {"history_messages": len(state.history), "has_summary": bool(state.summary), "pinned_notes": len(state.notes)}
                st.span.output = detail
                yield st.done_event(detail)

            # ---------------------------------------------------------- router
            async with Step("Router", "classify intent & rewrite query", input={"message": text}) as st:
                yield st.start_event()
                route = _heuristic_route(text)
                if llm.available:
                    try:
                        ctx = _memory_preamble(state)
                        convo = "\n".join(f"{m['role']}: {m['content'][:400]}" for m in state.history[-6:])
                        prompt = f"{ctx}\n\nRecent conversation:\n{convo or '(none)'}\n\nLatest user message:\n{text}"
                        data, _ = await llm.complete_json(ROUTER_SYSTEM, [{"role": "user", "content": prompt}], max_tokens=400, span_name="route")
                        if data and data.get("intent") in INTENTS:
                            rule_route = route
                            route = {**route, **{k: v for k, v in data.items() if v not in (None, "")}}
                            route["router"] = "llm"
                            # trust explicit evidence over the model for e-mail addresses
                            route["recipient"] = rule_route["recipient"] if not EMAIL_RE.search(text) else EMAIL_RE.search(text).group(0)
                    except Exception as exc:
                        st.span.set(llm_error=str(exc)[:200])
                route.setdefault("router", "rules")
                if route.get("source") not in (None, "notification", "press_release", "master_circular", "master_direction"):
                    route["source"] = None
                state.route = route
                st.span.output = route
                yield st.done_event({k: route.get(k) for k in ("intent", "standalone_query", "circular_ref", "since_days", "router")})

            intent = state.route.get("intent", "qa")
            if state.scope_id and intent in ("latest", "smalltalk"):
                intent = state.route["intent"] = "qa"  # scoped chat: every question is about that one circular
            handler = {
                "qa": _handle_qa,
                "latest": _handle_latest,
                "summarize": _handle_summarize,
                "email": _handle_email,
                "remember": _handle_remember,
                "smalltalk": _handle_smalltalk,
            }.get(intent, _handle_qa)
            async for ev in handler(state):
                yield ev

            # ---------------------------------------------------------- persist
            with session_scope() as db:
                am = Message(
                    conversation_id=state.conversation_id,
                    role="assistant",
                    content=state.answer,
                    citations=state.sources,
                    trace_id=tr.id,
                    meta={"intent": intent, "route": state.route, "verification": state.verification, "actions": state.actions,
                          "model": llm.model if llm.available else "none"},
                )
                db.add(am)
                db.flush()
                assistant_id = am.id

            async for ev in _update_memory(state):
                yield ev

            tr.output = {"intent": intent, "answer": state.answer[:2000], "sources": len(state.sources),
                         "verification": (state.verification or {}).get("verdict")}
            yield {"type": "done", "message_id": assistant_id, "trace_id": tr.id, "intent": intent,
                   "verification": state.verification, "actions": state.actions}
        except Exception as exc:
            log.exception("chat turn failed")
            tr.status = "error"
            yield {"type": "error", "message": f"The agents hit an error: {type(exc).__name__}: {exc}", "trace_id": tr.id}


# ------------------------------------------------------------------- handlers
async def _stream_answer(state: ChatState, system: str, user_prompt: str, agent: str = "Answer", label: str = "draft grounded answer"):
    llm = get_llm()
    async with Step(agent, label) as st:
        yield st.start_event()
        messages = _history_messages(state) + [{"role": "user", "content": user_prompt}]
        parts: list[str] = []
        try:
            async for delta in llm.stream(system, messages):
                parts.append(delta)
                yield {"type": "token", "text": delta}
        except Exception as exc:
            st.span.set(llm_error=str(exc)[:300])
            if not parts:
                raise
        state.answer = "".join(parts).strip()
        st.span.output = {"chars": len(state.answer)}
        yield st.done_event({"chars": len(state.answer), "model": llm.model})


def _sources_block(sources: list[dict]) -> str:
    out = []
    for s in sources:
        date = (s.get("published_at") or "")[:10]
        kind = s["source"].replace("_", " ") + (", superseded older version" if s.get("superseded") else "")
        out.append(f"[{s['n']}] {s['title']} ({kind}; {s.get('rbi_ref') or 'no RBI ref'}; {date})\n{s['text']}")
    return "\n\n".join(out)


async def _handle_qa(state: ChatState):
    s = get_settings()
    route = state.route
    query = route.get("standalone_query") or state.user_message
    since = datetime.now(timezone.utc) - timedelta(days=int(route["since_days"])) if route.get("since_days") else None
    async with Step("Retriever", "hybrid search (dense + BM25, RRF)", input={"query": query, "since_days": route.get("since_days")}) as st:
        yield st.start_event()
        circ_ids = [state.scope_id] if state.scope_id else None
        ref = route.get("circular_ref")
        if not circ_ids and ref and RBI_REF_RE.search(ref):
            with session_scope() as db:
                hit = db.query(Circular).filter(Circular.rbi_ref == RBI_REF_RE.search(ref).group(0)).first()
                circ_ids = [hit.id] if hit else None
        hits = await index.search(query, k=s.retrieval_top_k, source=None if state.scope_id else route.get("source"),
                                  since=None if state.scope_id else since, circular_ids=circ_ids,
                                  include_superseded=state.include_older)
        if not hits and not state.scope_id and (since or circ_ids):  # relax filters before giving up
            hits = await index.search(query, k=s.retrieval_top_k, include_superseded=state.include_older)
        state.sources = [h.to_dict(n=i + 1) for i, h in enumerate(hits)]
        st.span.output = [{k: v for k, v in x.items() if k != "text"} for x in state.sources]
        yield st.done_event({"hits": len(hits), "index_size": index.size})
    yield {"type": "sources", "items": state.sources}

    if not state.sources:
        state.answer = ("I could not find anything relevant in the indexed RBI publications. "
                        + ("The index is still empty — run a sync from the dashboard first." if index.size == 0
                           else "Try naming the topic, department or reference number (for example RBI/2026-27/302)."))
        yield {"type": "replace", "text": state.answer}
        state.verification = {"verdict": "Abstained", "score": None, "detail": "No sources retrieved.", "sentences": []}
        yield {"type": "verification", **state.verification}
        return

    llm = get_llm()
    prompt = f"{_memory_preamble(state)}\n\nSOURCES\n{_sources_block(state.sources)}\n\nQUESTION\n{state.user_message}"
    if llm.available:
        try:
            async for ev in _stream_answer(state, ANSWER_SYSTEM, prompt):
                yield ev
        except Exception as exc:
            yield {"type": "notice", "text": f"Language model unavailable ({type(exc).__name__}); showing the retrieved passages instead."}
            state.answer = ""
    if not state.answer:
        lines = ["Here are the most relevant passages from the indexed RBI publications:", ""]
        for src in state.sources[:4]:
            excerpt = re.sub(r"\s+", " ", src["text"])[:420]
            lines.append(f"- **{src['title']}** — {excerpt}… [{src['n']}]")
        state.answer = "\n".join(lines)
        yield {"type": "replace", "text": state.answer}

    async with Step("Verifier", "check citations & grounding") as st:
        yield st.start_event()
        state.verification = verify_answer(state.answer, state.sources)
        st.span.output = state.verification
        yield st.done_event({"verdict": state.verification["verdict"], "score": state.verification.get("score")})
    yield {"type": "verification", **state.verification}


def _recent_circulars(since_days: int | None, source: str | None, limit: int = 12) -> list[Circular]:
    with session_scope() as db:
        q = db.query(Circular)
        if source:
            q = q.filter(Circular.source == source)
        if since_days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=int(since_days))
            q2 = q.filter(or_(Circular.published_at >= cutoff, Circular.updated_at >= cutoff))
            rows = q2.order_by(Circular.published_at.desc()).limit(limit).all()
            if rows:
                return rows
        return q.order_by(Circular.published_at.desc().nullslast(), Circular.id.desc()).limit(limit).all()


async def _handle_latest(state: ChatState):
    route = state.route
    async with Step("Briefing", "collect recent publications", input={"since_days": route.get("since_days"), "source": route.get("source")}) as st:
        yield st.start_event()
        circs = _recent_circulars(route.get("since_days") or 7, route.get("source"))
        state.sources = [_circ_source(i + 1, c) for i, c in enumerate(circs)]
        st.span.output = {"count": len(circs)}
        yield st.done_event({"count": len(circs)})
    yield {"type": "sources", "items": state.sources}
    if not circs:
        state.answer = "Nothing has been indexed yet. Run a sync from the dashboard to pull the latest RBI publications."
        yield {"type": "replace", "text": state.answer}
        return
    listing = ["", "| # | Date | Type | Priority | Publication |", "|---|---|---|---|---|"]
    for src, c in zip(state.sources, circs):
        date = as_utc(c.published_at).strftime("%d %b") if c.published_at else "-"
        kind = c.source.replace("_", " ").capitalize() + (" (updated)" if c.revision else "")
        listing.append(f"| [{src['n']}] | {date} | {kind} | {c.priority} | [{c.title}]({c.url}) |")
    table = "\n".join(listing)
    llm = get_llm()
    if llm.available:
        prompt = "\n\n".join(f"[{src['n']}] {c.title} | {c.source.replace('_', ' ')}{' (updated)' if c.revision else ''} | priority {c.priority} | {src['text']}" for src, c in zip(state.sources, circs))
        try:
            async for ev in _stream_answer(state, BRIEFING_SYSTEM, prompt, agent="Briefing", label="write management briefing"):
                yield ev
            state.answer += "\n" + table
            yield {"type": "token", "text": "\n" + table}
            return
        except Exception as exc:
            yield {"type": "notice", "text": f"Language model unavailable ({type(exc).__name__}); showing the list only."}
    state.answer = f"Most recent RBI publications in the index:\n{table}"
    yield {"type": "replace", "text": state.answer}


async def _resolve_circulars(ref: str | None, query: str) -> list[Circular]:
    """Find the circular(s) the user means: reference number, 'latest', or best retrieval match."""
    latest_words = ("latest", "last", "most recent", "newest", "the latest", "latest circular")
    with session_scope() as db:
        if ref and RBI_REF_RE.search(ref):
            c = db.query(Circular).filter(Circular.rbi_ref == RBI_REF_RE.search(ref).group(0)).first()
            if c:
                return [c]
        if not ref or ref.lower().strip() in latest_words:
            c = db.query(Circular).order_by(Circular.published_at.desc().nullslast(), Circular.id.desc()).first()
            return [c] if c else []
    hits = await index.search(ref or query, k=5)
    if not hits:
        return []
    best = hits[0].record.circular_id
    with session_scope() as db:
        c = db.get(Circular, best)
        return [c] if c else []


async def _handle_summarize(state: ChatState):
    async with Step("Resolver", "identify circular", input={"circular_ref": state.route.get("circular_ref")}) as st:
        yield st.start_event()
        if state.scope_id:
            with session_scope() as db:
                one = db.get(Circular, state.scope_id)
                circs = [one] if one else []
        else:
            circs = await _resolve_circulars(state.route.get("circular_ref"), state.route.get("standalone_query") or state.user_message)
        st.span.output = [{"id": c.id, "title": c.title} for c in circs]
        yield st.done_event({"matched": [c.title[:80] for c in circs]})
    if not circs:
        state.answer = "I could not identify which circular you mean. Try its reference number or a distinctive phrase from the title."
        yield {"type": "replace", "text": state.answer}
        return
    c = circs[0]
    if not c.summary:
        async with Step("Summarizer", "summarize on demand", input={"circular_id": c.id}) as st:
            yield st.start_event()
            await summarize_circular(c.id)
            with session_scope() as db:
                c = db.get(Circular, c.id)
            yield st.done_event({"generated_by": (c.summary or {}).get("generated_by")})
    state.sources = [_circ_source(1, c)]
    yield {"type": "sources", "items": state.sources}
    state.answer = _summary_markdown(c, n=1)
    yield {"type": "replace", "text": state.answer}


async def _handle_email(state: ChatState):
    if not get_settings().email_enabled:
        state.answer = ("E-mail is switched off in this installation. You can copy this answer with the copy button, "
                        "or ask an administrator to set EMAIL_ENABLED=true.")
        yield {"type": "replace", "text": state.answer}
        return
    route = state.route
    user_email = state.user["email"]
    recipient = route.get("recipient")
    with session_scope() as db:
        allowed = set(e.lower() for e in (rs.get(db, "subscribers") or [])) | {
            e.lower() for (e,) in db.query(User.email).filter(User.is_active.is_(True)).all()
        }
    to = [user_email]
    async with Step("Notifier", "check recipient policy", input={"requested": recipient}) as st:
        yield st.start_event()
        if recipient and recipient.lower() != user_email.lower():
            if recipient.lower() in allowed:
                to = [recipient]
            else:
                st.span.output = {"allowed": False}
                yield st.done_event({"allowed": False})
                state.answer = (f"I can only e-mail registered users or configured subscribers, and **{recipient}** is neither. "
                                f"An administrator can add it under Settings → Alert recipients. I can send it to you ({user_email}) instead.")
                yield {"type": "replace", "text": state.answer}
                audit.record(user_email, "email.blocked", resource=recipient, details={"reason": "recipient not allow-listed"})
                return
        st.span.output = {"allowed": True, "to": to}
        yield st.done_event({"to": to})

    content = route.get("email_content") or ("circular" if route.get("circular_ref") else "answer")
    from app.observability.logging import current_trace_id

    tid = current_trace_id.get()
    if content == "digest":
        circs = _recent_circulars(route.get("since_days") or 7, route.get("source"))
        if not circs:
            state.answer = "There is nothing in the index to send yet."
            yield {"type": "replace", "text": state.answer}
            return
        subject, html_body, text_body = compose_digest(circs, tid, heading=f"Digest requested by {state.user['name']}.")
        ids = [c.id for c in circs]
        state.sources = [_circ_source(i + 1, c) for i, c in enumerate(circs)]
    elif content == "circular":
        circs = await _resolve_circulars(route.get("circular_ref"), route.get("standalone_query") or state.user_message)
        if not circs:
            state.answer = "I could not identify the circular to send. Please give its reference number or title."
            yield {"type": "replace", "text": state.answer}
            return
        c = circs[0]
        if not c.summary:
            await summarize_circular(c.id)
            with session_scope() as db:
                c = db.get(Circular, c.id)
        subject, html_body, text_body = compose_alert(c, tid)
        ids = [c.id]
        state.sources = [_circ_source(1, c)]
    else:
        with session_scope() as db:
            last = (
                db.query(Message)
                .filter(Message.conversation_id == state.conversation_id, Message.role == "assistant")
                .order_by(Message.id.desc())
                .first()
            )
            prev_q = (
                db.query(Message)
                .filter(Message.conversation_id == state.conversation_id, Message.role == "user", Message.id < (last.id if last else 0))
                .order_by(Message.id.desc())
                .first()
            )
        if not last:
            state.answer = "There is no earlier answer in this conversation to e-mail. Ask a question first, or ask me to e-mail a digest."
            yield {"type": "replace", "text": state.answer}
            return
        subject, html_body, text_body = compose_answer(prev_q.content if prev_q else "Your question", last.content, last.citations or [], tid)
        ids = sorted({c["circular_id"] for c in (last.citations or []) if c.get("circular_id")})

    async with Step("Notifier", f"send {content} e-mail", input={"to": to, "subject": subject}) as st:
        yield st.start_event()
        result = await send_email(content if content != "circular" else "summary", to, subject, html_body, text_body,
                                  circular_ids=ids, triggered_by=user_email)
        st.span.output = result
        yield st.done_event(result)
    state.actions.append({"type": "email", **result, "subject": subject})
    if state.sources:
        yield {"type": "sources", "items": state.sources}
    verb = {"sent": "Sent", "dry_run": "Prepared (dry run — SMTP password not configured, saved to the outbox)",
            "disabled": "Not sent — e-mail is disabled in settings", "failed": "Failed to send"}[result["status"]]
    state.answer = f"{verb}: **{subject}** → {', '.join(result['recipients'])}."
    if result.get("error"):
        state.answer += f"\n\nError: `{result['error']}`"
    yield {"type": "replace", "text": state.answer}


async def _handle_remember(state: ChatState):
    note = (state.route.get("memory_note") or state.user_message).strip()
    async with Step("Memory", "save long-term note", input={"note": note}) as st:
        yield st.start_event()
        with session_scope() as db:
            db.add(MemoryNote(user_id=state.user["id"], content=note[:500], source_message_id=state.user_message_id))
        st.span.output = {"saved": note}
        yield st.done_event({"saved": note[:120]})
    audit.record(state.user["email"], "memory.save", resource="memory_note", details={"note": note[:200]})
    state.answer = f"Noted — I'll keep this in mind in future conversations: _{note}_\n\nYou can review or delete saved notes in the memory panel."
    yield {"type": "replace", "text": state.answer}


async def _handle_smalltalk(state: ChatState):
    llm = get_llm()
    if llm.available:
        try:
            async for ev in _stream_answer(state, SMALLTALK_SYSTEM + "\n\n" + _memory_preamble(state), state.user_message, label="reply"):
                yield ev
            return
        except Exception:
            pass
    state.answer = (f"Hello {state.user['name'].split()[0]}. I watch the RBI website for new circulars, notifications and press "
                    "releases, index them, and e-mail alerts. Ask me a question about any indexed publication, ask what is new "
                    "this week, ask for a summary of a circular, or ask me to e-mail you a digest.")
    yield {"type": "replace", "text": state.answer}


async def _update_memory(state: ChatState):
    s = get_settings()
    llm = get_llm()
    with session_scope() as db:
        conv = db.get(Conversation, state.conversation_id)
        pending = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id, Message.id > conv.summary_upto_message_id)
            .order_by(Message.id)
            .all()
        )
        pending_data = [(m.id, m.role, m.content) for m in pending]
        prior = conv.summary or ""
    if len(pending_data) < s.memory_summarize_every or not llm.available:
        return
    async with Step("Memory", "compress conversation into long-term summary", input={"messages": len(pending_data)}) as st:
        yield st.start_event()
        keep = s.memory_window_messages // 2
        to_fold = pending_data[:-keep] if keep else pending_data
        transcript = "\n".join(f"{role}: {content[:800]}" for _, role, content in to_fold)
        try:
            res = await llm.complete(MEMORY_SYSTEM, [{"role": "user", "content": f"Current summary:\n{prior or '(empty)'}\n\nNew turns:\n{transcript}"}],
                                     max_tokens=300, span_name="memory.summarize")
            new_summary = res.text.strip()[:2000]
            with session_scope() as db:
                conv = db.get(Conversation, state.conversation_id)
                conv.summary = new_summary
                conv.summary_upto_message_id = to_fold[-1][0]
            st.span.output = {"summary": new_summary, "folded_messages": len(to_fold)}
            yield st.done_event({"folded_messages": len(to_fold)})
            yield {"type": "memory", "summary": new_summary}
        except Exception as exc:
            st.span.set(llm_error=str(exc)[:200])
            yield st.done_event({"skipped": "model unavailable"})
