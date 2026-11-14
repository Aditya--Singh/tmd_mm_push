"""Central configuration. Every value can be overridden through environment variables or a .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore", case_sensitive=False)

    # ---- Application ------------------------------------------------------
    app_name: str = "PNB Regulatory Sentinel"
    org_name: str = "Punjab National Bank"
    org_short: str = "PNB"
    org_unit: str = "Data Analytics and Strategic Innovation Division"
    environment: str = "dev"
    data_dir: Path = Path("./data")
    database_url: str = ""  # empty -> SQLite file inside data_dir
    public_url: str = "http://localhost:8090"  # used for links inside alert e-mails
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"  # add the dashboard's origin to call the API
    # Which sites may show this app inside an iframe (Content-Security-Policy frame-ancestors).
    # "*" = any; for production list the Top Management Dashboard origin, e.g. "https://tmd.pnb.bank.in".
    frame_ancestors: str = "*"
    log_level: str = "INFO"

    # ---- Security ---------------------------------------------------------
    # Off by default: the app is meant to sit behind the Top Management Dashboard's own sign-in.
    # Everyone then acts as the default user below. Turn on for stand-alone use.
    auth_enabled: bool = False
    jwt_secret: str = "change-this-secret-in-production"
    jwt_expiry_minutes: int = 480
    admin_email: str = "sireejaa.uppal@pnb.bank.in"
    admin_password: str = "ChangeMe@123"
    admin_name: str = "Sireejaa Uppal"
    login_max_failures: int = 5
    login_lockout_minutes: int = 10

    # ---- The Executive Intelligence Hub -----------------------------------
    # The hub owns the sign-in and vouches for the person. It asks this server for a
    # single-use ticket, with this shared secret, which stays on its server.
    handoff_secret: str = ""
    handoff_ticket_seconds: int = 120
    # The hub accounts that are administrators in this app as well (comma separated).
    handoff_admin_users: str = "admin"
    # Which sites may show this app in an iframe. The hub's own address.
    embed_parent_origins: str = "http://localhost:5174,http://127.0.0.1:5174"

    # ---- RBI sources ------------------------------------------------------
    # comma separated "source=url" pairs. Local paths / file:// URLs are allowed (useful for testing).
    rbi_feeds: str = (
        "notification=https://rbi.org.in/notifications_rss.xml,"
        "press_release=https://rbi.org.in/pressreleases_rss.xml"
    )
    # RBI listing pages (no RSS exists for these). Set either to "" to switch it off.
    master_circulars_url: str = "https://rbi.org.in/Scripts/BS_ViewMasterCirculardetails.aspx"
    master_directions_url: str = "https://rbi.org.in/Scripts/BS_ViewMasterDirections.aspx"
    master_circular_years: str = "all"  # "all" financial years, or a number of years back from the current one
    master_circular_archive_refresh_hours: int = 24  # older years rarely change: re-read them once a day
    chromium_path: str = ""  # optional: an existing Chrome/Chromium binary for reading the year archive
    max_items_per_sync: int = 60  # documents ingested per run
    backfill_continuous: bool = True  # while a backlog remains, start the next run straight away
    summarize_baseline_with_llm: bool = False  # first-time backlog gets rule summaries; AI summary queue below
    ai_summary_queue_enabled: bool = True  # in the background, give every document an AI summary over time
    ai_summary_batch: int = 6  # documents per background round
    ai_summary_interval_minutes: int = 5
    sync_interval_minutes: int = 30
    sync_on_startup: bool = True
    notify_on_first_sync: bool = False  # first sync only builds the baseline, no e-mail flood
    digest_threshold: int = 4  # >= this many new items in one run -> one digest e-mail instead of many
    fetch_detail_page: bool = True  # visit each circular page to discover the PDF link
    http_verify_ssl: bool = True
    http_timeout_seconds: float = 30.0
    http_user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0 Safari/537.36 RBI-Sentinel/1.0"
    )
    polite_delay_seconds: float = 1.0

    # ---- E-mail -----------------------------------------------------------
    email_enabled: bool = False  # alerts and "e-mail me" are switched off unless set to true
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_use_starttls: bool = True
    smtp_username: str = "sireejaa16@gmail.com"
    smtp_password: str = ""  # Gmail App Password. Empty -> dry-run (e-mails written to data/outbox)
    email_from: str = "sireejaa16@gmail.com"
    email_from_name: str = "PNB RBI Sentinel"
    default_recipients: str = "sireejaa.uppal@pnb.bank.in"

    # ---- LLM --------------------------------------------------------------
    llm_provider: str = "openai_compat"  # openai_compat | anthropic | none
    llm_base_url: str = "http://localhost:11434/v1"  # Ollama default; vLLM: http://localhost:8001/v1
    llm_api_key: str = "ollama"
    # "auto" uses the best model that is installed on this machine. A name is used as it
    # is when it is installed, and the best installed model is used instead when it is
    # not.
    llm_model: str = "auto"
    # With "auto", a model that is named but not installed is a reason to say so.
    llm_strict_model: bool = False
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1800
    llm_timeout_seconds: float = 180.0
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    # Where the models of this machine are listed: Ollama's own address, without /v1.
    ollama_url: str = "http://localhost:11434"

    # ---- Embeddings / retrieval ------------------------------------------
    embedding_provider: str = "fastembed"  # fastembed | openai_compat | hash
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_base_url: str = ""  # defaults to llm_base_url for openai_compat
    reranker_enabled: bool = False
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    chunk_size_words: int = 220
    chunk_overlap_words: int = 40
    retrieval_top_k: int = 6
    retrieval_candidates: int = 30
    rrf_k: int = 60

    # ---- Conversational memory -------------------------------------------
    memory_window_messages: int = 8
    memory_summarize_every: int = 6

    # ---- Derived ----------------------------------------------------------
    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'sentinel.db').resolve()}"

    @property
    def feeds(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for part in self.rbi_feeds.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" in part and not part.startswith("http"):
                src, url = part.split("=", 1)
            else:
                src, url = "notification", part
            out.append((src.strip(), url.strip()))
        return out

    @property
    def smtp_dry_run(self) -> bool:
        """No real sending when there is no mail host, or a login name is set without its password."""
        return not self.smtp_host or (bool(self.smtp_username) and not self.smtp_password)

    @property
    def mc_years_limit(self) -> int | None:
        v = str(self.master_circular_years).strip().lower()
        return None if v in ("", "all", "*") else max(0, int(v))

    @property
    def page_sources(self) -> list[tuple[str, str]]:
        out = []
        if self.master_circulars_url:
            out.append(("master_circular", self.master_circulars_url))
        if self.master_directions_url:
            out.append(("master_direction", self.master_directions_url))
        return out

    @property
    def recipient_list(self) -> list[str]:
        return [e.strip() for e in self.default_recipients.split(",") if e.strip()]

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    (s.data_dir / "logs").mkdir(exist_ok=True)
    (s.data_dir / "outbox").mkdir(exist_ok=True)
    return s
