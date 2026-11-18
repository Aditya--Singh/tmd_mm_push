"""Central configuration. Every value can be overridden through environment variables or a .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Application ------------------------------------------------------
    app_name: str = "PNB Data Analyzer"
    org_name: str = "Punjab National Bank"
    org_short: str = "PNB"
    org_unit: str = "Data Analytics and Strategic Innovation Division"
    environment: str = "dev"
    data_dir: Path = Path("./data")
    database_url: str = ""  # empty -> SQLite file inside data_dir
    public_url: str = "http://localhost:8095"
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"
    frame_ancestors: str = "*"
    log_level: str = "INFO"

    # ---- Security ---------------------------------------------------------
    jwt_secret: str = "change-this-secret-in-production"
    jwt_expiry_minutes: int = 480

    # ---- The Executive Intelligence Hub -----------------------------------
    # The hub owns the sign-in and vouches for the person. It asks this server for a
    # single-use ticket, with this shared secret, which stays on its server.
    handoff_secret: str = ""
    handoff_ticket_seconds: int = 120
    # Which sites may drive this app. The hub's own address.
    embed_parent_origins: str = "http://localhost:5174,http://127.0.0.1:5174"

    # ---- The documents ----------------------------------------------------
    max_upload_bytes: int = 25 * 1024 * 1024
    preview_rows: int = 50
    max_plots: int = 12

    # ---- The language model ------------------------------------------------
    # "auto" uses the best model that is installed on this machine, which is what most
    # machines want. Name a model to pin it, for example LLM_MODEL=qwen3:8b.
    llm_provider: str = "openai_compat"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "auto"
    llm_strict_model: bool = False
    ollama_url: str = "http://localhost:11434"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1200
    llm_timeout_seconds: float = 180.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    """Forget the settings, so that a change in the environment is noticed."""
    get_settings.cache_clear()
