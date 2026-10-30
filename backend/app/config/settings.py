import sys
from functools import lru_cache
from pathlib import Path

from loguru import logger
from pydantic import ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# backend/app/config/settings.py -> backend -> repository root
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

PLACEHOLDER_SECRET = "change-me-generate-a-random-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # The environment file in the backend directory takes precedence.
        # A file in the repository root is read as a fallback, so the
        # backend can be started from either directory.
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        extra="ignore",
    )

    database_url: str = "sqlite:///news.db"

    app_name: str = "Bank News AI"

    # Names the environment the backend is running in, for example
    # development or production.
    env: str = "development"

    ollama_base_url: str = "http://localhost:11434"

    ollama_model: str = "qwen3:8b"

    timezone: str = "Asia/Kolkata"

    news_cutoff_date: str = "2026-06-20"

    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 480

    # Comma-separated list of browser origins allowed to call the API.
    # Includes the news frontend (5173) and the landing page hub (5174).
    cors_origins: str = (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "http://newsintel.pnbbank.in:5173,"
        "http://localhost:5174,"
        "http://127.0.0.1:5174,"
        "http://newsintel.pnbbank.in:5174"
    )

    # Peer Benchmarking, which the landing page opens in its workspace.
    #
    # The landing page asks the benchmarking app for a single-use sign-in ticket on behalf of
    # the person who signed in here. The shared secret never leaves this server.
    kpi_app_url: str = "http://127.0.0.1:8077"

    # The same value as HANDOFF_SECRET in the benchmarking app's .env.
    # While it is empty, the Peer Benchmarking workspace stays closed and says why.
    kpi_handoff_secret: str = ""

    kpi_request_timeout: float = 10.0

    @model_validator(mode="after")
    def validate_secret_key(self):
        if not self.jwt_secret_key.strip():
            raise ValueError(
                "JWT_SECRET_KEY is not set.\n"
                "Copy the example environment file and give it a random "
                "value:\n"
                "    cp backend/.env.example backend/.env\n"
                "    python -c \"import secrets; "
                "print(secrets.token_urlsafe(48))\"\n"
                "then put the generated value in JWT_SECRET_KEY."
            )

        if self.jwt_secret_key == PLACEHOLDER_SECRET:
            logger.warning(
                "JWT_SECRET_KEY still holds the example value. Generate a "
                "real one before this is used anywhere but on a developer "
                "machine."
            )

        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Singleton instance
try:
    settings = get_settings()
except ValidationError as exc:
    # Report a configuration problem as a readable message instead of a
    # traceback, because the usual cause is a missing .env file.
    detail = exc.errors()[0].get("msg", str(exc))

    print(
        "\n"
        "=========================================================\n"
        "The backend is not configured yet.\n"
        "=========================================================\n"
        f"{detail}\n",
        file=sys.stderr,
    )

    raise SystemExit(1) from None
