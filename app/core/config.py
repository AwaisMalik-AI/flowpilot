"""Application settings loaded from environment (no hardcoded secrets)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "FlowPilot"
    DEBUG: bool = False

    DATABASE_URL: str = Field(
        ...,
        description="SQLAlchemy URL, e.g. postgresql+psycopg2://user:pass@host:5432/db",
    )
    REDIS_URL: str = Field(..., description="Redis URL for Celery broker/backend")

    SECRET_KEY: str = Field(..., min_length=32, description="Signing key for JWT and internal tokens")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    WEBHOOK_SECRET: str = Field(
        ...,
        min_length=16,
        description="HMAC / signing material for verifying incoming webhook payloads when configured",
    )

    CELERY_BROKER_URL: str = Field(default="", description="Defaults to REDIS_URL if empty")
    CELERY_RESULT_BACKEND: str = Field(default="", description="Defaults to REDIS_URL if empty")
    CELERY_TASK_ALWAYS_EAGER: bool = False

    MAX_WORKFLOW_STEPS: int = Field(default=500, ge=1, le=100_000)
    EXECUTION_TIMEOUT_SECONDS: int = Field(default=3600, ge=1, le=86400)

    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    API_PREFIX: str = "/api"

    LLM_API_KEY: str | None = None
    LLM_BASE_URL: str | None = None
    LLM_MODEL: str = "gpt-4o-mini"

    @model_validator(mode="after")
    def celery_defaults_from_redis(self):
        r = str(self.REDIS_URL)
        if not self.CELERY_BROKER_URL:
            object.__setattr__(self, "CELERY_BROKER_URL", r)
        if not self.CELERY_RESULT_BACKEND:
            object.__setattr__(self, "CELERY_RESULT_BACKEND", r)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
