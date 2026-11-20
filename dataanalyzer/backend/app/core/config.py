"""Central configuration.

Every value can be overridden through an environment variable or a `.env` file. The
settings are read with the **first** occurrence winning, which is the rule the whole
platform uses, so a value set in the shell wins over the one in the file.

The names of the language model and of the grammar checker are the upstream's, so the
upstream's modules work unchanged. The names of the hub's settings are the platform's.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

#: The backend's own directory, so the `.env` file is found wherever the app is run from.
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"),
        extra="ignore",
        case_sensitive=False,
    )

    # ---- The language model ------------------------------------------------
    # The local model server. Only a local host may be used, so no document ever leaves
    # this machine.
    ollama_url: str = "http://localhost:11434"
    # The model to use. The setup writes the best model that is really installed.
    ollama_model: str = "gpt-oss:20b"
    ollama_num_ctx: int = 32768

    # ---- The grammar checker, which is optional ----------------------------
    # LanguageTool is a separate local service. The app works without it and says so.
    languagetool_url: str = "http://localhost:8120"
    languagetool_language: str = "en-GB"

    # ---- The uploads --------------------------------------------------------
    max_upload_mb: int = 20
    data_dir: str = str(BACKEND_DIR / "data")

    # ---- The web ------------------------------------------------------------
    # Who may call this app from a browser, who may frame it, and who may drive it
    # over the message bridge. The hub's own address.
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"
    frame_ancestors: str = "http://localhost:5174,http://127.0.0.1:5174"
    embed_parent_origins: str = "http://localhost:5174,http://127.0.0.1:5174"

    # ---- Security ----------------------------------------------------------
    # The app's own signing key, for the tokens it issues.
    jwt_secret: str = "change-this-secret-in-production"
    jwt_expiry_minutes: int = 480

    # ---- The Executive Intelligence Hub -------------------------------------
    # The secret the hub and this app share. It stays on the hub's server.
    handoff_secret: str = ""
    handoff_ticket_seconds: int = 120

    @property
    def max_upload_bytes(self) -> int:
        """The largest upload, in bytes."""
        return self.max_upload_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def frame_ancestor_list(self) -> list[str]:
        return [o.strip() for o in self.frame_ancestors.split(",") if o.strip()]

    @property
    def embed_parent_origin_list(self) -> list[str]:
        return [o.strip() for o in self.embed_parent_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """The settings, read once."""
    return Settings()
