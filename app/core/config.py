from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Normalize DATABASE_URL for SQLAlchemy + Render Postgres.

    Render injects Postgres URLs as ``postgres://...`` (or plain
    ``postgresql://...``). SQLAlchemy with the installed ``psycopg`` (v3)
    driver needs ``postgresql+psycopg://...``. SQLite URLs pass through.
    """
    value = (url or "").strip()
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    app_version: str = "1.0.0"
    demo_mode: bool = True
    database_url: str = "sqlite:///./student_diagnostics.db"
    frontend_url: str = "http://localhost:3000"
    secret_key: str = "development-only-secret"
    ai_provider: Literal["mock", "gemini", "openai", "anthropic"] = "mock"
    ai_model: str = "mock-educator-v1"
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_timeout_seconds: int = 60
    weak_threshold: float = Field(default=0.50, ge=0, le=1)
    developing_threshold: float = Field(default=0.70, ge=0, le=1)
    strong_threshold: float = Field(default=0.85, ge=0, le=1)

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_database_url(value)
        return value

    @property
    def frontend_origins(self) -> list[str]:
        """FRONTEND_URL as a list. Supports comma-separated values for Render.

        Example: ``https://app.onrender.com,https://example.com``.
        """
        return [part.strip() for part in self.frontend_url.split(",") if part.strip()]

    @model_validator(mode="after")
    def thresholds_are_ordered(self) -> "Settings":
        if not self.weak_threshold < self.developing_threshold < self.strong_threshold:
            raise ValueError("Thresholds must satisfy weak < developing < strong")
        if self.app_env == "production" and self.secret_key == "development-only-secret":
            raise ValueError("SECRET_KEY must be changed in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

