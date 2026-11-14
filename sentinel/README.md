# PNB Regulatory Sentinel

> **New here? Open [START_HERE.md](START_HERE.md)** for step-by-step instructions to get it running on the GB10.
> **Windows, restarts and health checks, backups, updates, GitHub: [MANUAL.md](MANUAL.md).**
> **Integrating into the Top Management Dashboard? Open [INTEGRATION.md](INTEGRATION.md).**
>
> Login and e-mail are **off by default** (`AUTH_ENABLED=false`, `EMAIL_ENABLED=false`); the code for both is
> still here and switches on from `.env`.

An agentic GenAI application, in Punjab National Bank's maroon-and-gold theme, that watches the Reserve Bank of India
website — **Notifications (circulars), Press Releases, Master Circulars and Master Directions** — files every new or
revised document into a searchable knowledge base (RAG), e-mails an alert, and answers questions with citations,
while recording **every agent step** in traces, logs and a tamper-evident audit trail.

```
            ┌──────────── every 30 min (APScheduler) ───────────┐
RBI RSS feeds ─┐
Master Circular│ Watcher ─► Ingestion ─► Summarizer ─► Indexer ─► Notifier ──► SMTP (sireejaa16@gmail.com
and Direction ─┘└───────────────────────────────────────────────────┘           → sireejaa.uppal@pnb.bank.in)
listing pages
                              │ chunks + embeddings + brief
                              ▼
                     SQLite / PostgreSQL  ◄──── traces · spans · audit chain · e-mail log · feedback
                              ▲
User ─► Login ─► Assistant ─► Memory ─► Router ─► Retriever (dense + BM25, RRF) ─► Answer ─► Verifier ─► Memory
                                          └─► Briefing | Resolver ─► Summarizer | Notifier (e-mail) | Remember
```

## What you get

| Requirement | Where it lives |
|---|---|
| Automatic fetch of RBI notifications & circulars | `agents/ingestion.py` — RBI RSS feeds (`notifications_rss.xml`, `pressreleases_rss.xml`), detail page + PDF link discovery, PDF text fallback |
| **Every financial year of Master Circulars** | RBI's year links are page scripts, so a headless Chromium (Playwright) clicks each year, Archives included, and parses each table; older years are re-read once a day (`MASTER_CIRCULAR_YEARS=all`). Yearly versions of the same circular are linked: the newest is used for answers, older ones are labelled "Older version" and searchable on request |
| **Per-circular AI summary** | Background queue gives every current document an AI summary; opening a circular without one writes it immediately. `POST /api/circulars/{id}/summarize` for the dashboard |
| **One RAG over everything + chat with one circular** | The Assistant searches all sources together; "Chat with this circular" (`circular_id`) limits retrieval to one document |
| **Master Circulars and Master Directions** | `agents/rbi_pages.py` reads `BS_ViewMasterCirculardetails.aspx` and `BS_ViewMasterDirections.aspx` (no RSS exists): department heading, date, title, detail page and PDF for every entry. Full text comes from the detail page (PDF fallback). **Revisions are detected** — RBI keeps the id and changes the title ("Updated as on …"), so the document is re-indexed and an "Updated" alert goes out. Earlier Master Circular years are attempted through the page's form post and the outcome is recorded in the trace |
| Big first load without an e-mail flood | Each source has its own silent baseline. The ~250 Master Directions are read `MAX_ITEMS_PER_SYNC` at a time; alerts start for a source only once its baseline is complete. Backlog documents get fast rule-based briefs, with an AI summary one click away |
| PNB applicability | Rules read the title, the addressee list and the RBI listing heading (e.g. "Commercial Banks", "Co-operative Banking", "Financial Inclusion and Development"). Where the title or addressees name the entity type explicitly, the rule's verdict is kept even if the AI model reads it differently, and the model's view is shown alongside |
| Added to the RAG | Structure-aware chunking with contextual headers, local embeddings (`bge-m3` on Ollama by default; fastembed on CPU as an option), hybrid dense + BM25 search fused with Reciprocal Rank Fusion, optional cross-encoder rerank (`rag/`) |
| E-mail on every new circular | `agents/notifier.py` — branded HTML alert per item, or one digest when many arrive; first run builds a silent baseline so you are not flooded with ~20 old items |
| Chatbot with memory | Short-term window + rolling conversation summary (Memory agent) + long-term "remember that…" notes the user can see and delete |
| Summarisation | Structured brief per circular: headline, key points, **action for the bank**, applicability to a scheduled commercial bank, priority, effective date — rules first, LLM refines, both views kept |
| E-mail support in chat | "E-mail me this answer", "e-mail me this week's digest", "e-mail RBI/2026-27/302". Recipients are restricted to registered users and configured subscribers (prevents data leaving to arbitrary addresses) |
| Login page | JWT sessions, bcrypt passwords, lock-out after 5 failures, admin/analyst roles, forced password change for new accounts |
| Logs | Structured JSON logs (`data/logs/app.jsonl`) where every line carries `trace_id` / `agent`; live tail in the UI |
| Observability & transparency | Every chat turn, sync run and e-mail is a **trace**; every agent step is a **span** with input, output, model, tokens (OpenTelemetry GenAI attribute names), latency and errors. The UI shows a live "routing slip" for each answer and a waterfall per trace |
| Auditability | Hash-chained audit trail (each record stores SHA-256 of itself + previous hash). One click verifies the whole chain and pinpoints a tampered row; CSV export |
| Feedback | Thumbs up/down per answer with reason tags and comments, linked to the exact trace; overall product rating; satisfaction KPIs |
| Grounding check | Verifier agent scores each answer: citation validity, share of sentences cited, lexical support of the cited passages |

## Technology

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, APScheduler, httpx, feedparser, BeautifulSoup, pypdf, NumPy, rank-bm25, fastembed (ONNX), OpenAI SDK (any OpenAI-compatible server) and Anthropic SDK.
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS 4, React Router 7, Recharts, react-markdown; self-hosted fonts (works on an intranet without Google Fonts). PNB maroon/gold theme with light and dark modes; colours are tokens at the top of `frontend/src/index.css` (and in `backend/app/agents/notifier.py` for e-mails). Drop the official logo at `frontend/public/brand/logo.png`; otherwise a plain "PNB" badge is shown.
- **Models:** model-agnostic. Default is `gpt-oss:20b` for answers and `bge-m3` for embeddings, both on Ollama on the GB10. vLLM, OpenAI/Azure, or Claude work by changing `.env`. With `LLM_PROVIDER=none` the whole app still runs on rules and extractive summaries.

## Run it

Full beginner steps: **[START_HERE.md](START_HERE.md)**. Short version for the GB10:

```bash
ollama pull gpt-oss:20b && ollama pull bge-m3
cp .env.example .env                   # defaults suit the GB10; login and e-mail are off
docker compose up -d --build           # host networking; opens on http://<gb10-ip>:8090
python3 scripts/check.py               # GPU, Ollama, models, container, sources, summaries
```

Windows (Docker Desktop): set `COMPOSE_FILE=docker-compose.windows.yml` in `.env`, then the same commands; see MANUAL.md Part C.
Without Docker: `./run.sh` (serve), `./run.sh dev` (hot reload), `./run.sh test` (tests); on Windows `run.ps1`.

## Using it

- **Assistant** — ask anything about indexed publications. Click a numbered citation to see the exact passage and why it was retrieved (semantic rank, keyword rank, fused score). The right-hand *routing slip* shows each agent that handled the question, what it decided and how long it took. Try:
  - "What is new from the RBI this week, and what needs action?"
  - "Summarise RBI/2026-27/302"
  - "Summarise the Master Circular on credit facilities to SCs and STs"
  - "Under the master direction, when does a term loan become an NPA?"
  - "What is the minimum leverage ratio for a D-SIB?"
  - "Remember that I review circulars for the Treasury division"
  - "E-mail me this answer"
- **Circulars** — filter by priority and applicability; each page shows the brief, the rules-vs-model view, the e-mails sent and a link to the ingestion trace.
- **Agent traces** — waterfall of every run; click a step to see its input and output JSON, model and token counts.
- **Logs / Audit trail** (administrators) — live JSON logs; hash-chain verification and CSV export.
- **Feedback** — satisfaction, most-reported problems, each item linked to its trace.

## How transparency works (one chat turn)

1. Your message is saved, then a **trace** opens and an audit record `chat.query` is chained into the audit log with that trace id.
2. **Memory** loads the last few messages, the conversation summary and your saved notes.
3. **Router** (LLM with a rules fallback) classifies the intent and rewrites the question so it stands alone.
4. **Retriever** runs semantic and keyword search separately and fuses the rankings (RRF), so exact reference numbers and paraphrased questions both work.
5. **Answer** writes from the numbered sources only, citing each sentence; if the sources do not cover it, it says so.
6. **Verifier** checks every citation points to a real source and how much of each cited sentence is supported by that source.
7. **Memory** compresses long conversations into a summary so context is not lost.

Each step is a span in the database (visible in *Agent traces*), a line in the logs with the same `trace_id`, and a live step in the UI.

## Project layout

```
backend/
  app/main.py                 FastAPI app, start-up, static UI
  app/config.py               all settings (.env)
  app/scheduler.py            periodic RBI check
  app/agents/ingestion.py     Watcher, Ingestion, Summarizer
  app/agents/rbi_pages.py     Master Circular / Master Direction listing-page reader
  app/agents/notifier.py      e-mail composition + SMTP
  app/agents/pipeline.py      sync orchestration
  app/agents/chat.py          conversational agent graph + Verifier
  app/rag/text.py             HTML/PDF → text, metadata, applicability & priority rules, chunking
  app/rag/index.py            hybrid index (dense + BM25 + RRF, rerank)
  app/llm/                    LLM providers, embeddings
  app/observability/          tracer, JSON logging, hash-chained audit, live event bus
  app/api/                    REST + SSE endpoints
  tests/                      end-to-end tests (offline RSS fixtures, fake OpenAI-compatible model)
frontend/src/                 React UI (pages/, components/, lib/)
scripts/check.py              health check (GPU, Ollama, container, app, sources); Python standard library only
docker-compose.windows.yml    Docker Desktop variant (port mapping, host.docker.internal)
run.ps1                       Windows run without Docker
```

## Tests

`./run.sh test` runs an end-to-end suite against saved copies of RBI feeds and listing pages: login and lock-out,
sync and idempotency, Master Circular / Master Direction parsing, applicability rules, revision detection,
metadata extraction, applicability, alerts (dry-run), chat with citations and trace, memory, feedback, the e-mail
recipient policy, summaries, dashboard, settings, and **audit-chain tamper detection**. To exercise the LLM path
offline: `uvicorn tests.fake_llm:app --port 9911` and run the tests with
`TEST_LLM_PROVIDER=openai_compat LLM_BASE_URL=http://127.0.0.1:9911/v1`.

## Before this goes beyond a pilot — honest notes

- **E-mail route.** Sending from a personal Gmail account into the bank's mail domain is fine for a personal pilot, but
  it will likely conflict with the bank's information-security policy for anything official, and the bank's gateway may
  quarantine it. For production, point `SMTP_HOST` at the bank's internal relay and use a service mailbox.
- **RBI website.** The RSS feeds carry the full circular text. The Master Circular and Master Direction pages have no
  feed, so they are read as web pages; the parser does not depend on CSS classes, but a redesign of those pages can
  still break it. If that happens the Overview shows "read 0 entries" for that source instead of failing silently.
  Earlier Master Circular years are loaded by RBI's own page script, which could not be inspected while building this;
  the first live run records in its trace whether that worked. Keep `POLITE_DELAY_SECONDS` ≥ 1.
- **The Verifier is a fast proxy**, not proof of correctness. Lexical overlap catches unsupported sentences and bad
  citations but not subtle misreadings. For production, add an NLI / hallucination-evaluation model (e.g. HHEM) as a
  second judge and evaluate against a golden question set (RAGAS) before rollout.
- **Single process by design.** The search index, live event stream and audit-chain lock live in one Uvicorn worker.
  That is ample for a department. For many users, move to PostgreSQL + pgvector and a database-level lock for the
  audit chain.
- **Security hardening.** Put it behind the bank's TLS reverse proxy / SSO, set a strong `JWT_SECRET`, and consider
  moving the session token from browser storage to an HttpOnly cookie.
- **Model choice.** Summaries and priority/applicability verdicts are advisory. The UI always shows the rules-engine
  view next to the model's view so disagreements are visible, and every e-mail tells readers to check the original.
