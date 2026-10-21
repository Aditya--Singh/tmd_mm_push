from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "sqlite:///news.db"

    ollama_base_url: str = "http://localhost:11434"

    ollama_model: str = "qwen3:8b"

    timezone: str = "Asia/Kolkata"

    news_cutoff_date: str = "2026-06-20"

    jwt_secret_key: str
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
settings = get_settings()
