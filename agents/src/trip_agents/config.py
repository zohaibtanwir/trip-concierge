"""Settings for the agents project.

Reads `../backend/.env` so secrets are not duplicated across projects.
Accepts either LANGFUSE_HOST (canonical, matches the Langfuse SDK's
default env var) or LANGFUSE_BASE_URL (what the local .env happened to
have first). Either keeps the project working.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py lives at agents/src/trip_agents/config.py — repo root is THREE
# parents up (was two pre-src-layout). Slice 2.5a missed this; the env-file
# fallback was silently pointing at a nonexistent path. Shell env still won,
# which is why nothing visibly broke.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BACKEND_ENV = _REPO_ROOT / "backend" / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-sonnet-4-6",
        validation_alias="ANTHROPIC_MODEL",
    )

    tavily_api_key: str = Field(default="", validation_alias="TAVILY_API_KEY")

    langfuse_public_key: str = Field(default="", validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", validation_alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices("LANGFUSE_HOST", "LANGFUSE_BASE_URL"),
    )
    # Slice 4d0 — Langfuse SDK v4 does NOT auto-read LANGFUSE_ENVIRONMENT
    # from os.environ (verified empirically against cloud.langfuse.com:
    # test trace with env var set landed in environment="default"; trace
    # with explicit Langfuse(environment=...) kwarg landed in
    # environment="production"). The env var must be passed as a
    # constructor kwarg via get_langfuse(). Default "default" preserves
    # existing trace partition behavior for callers that don't set the
    # var — backward-compat for the 1020 default-partition traces.
    langfuse_environment: str = Field(
        default="default",
        validation_alias="LANGFUSE_ENVIRONMENT",
    )

    redis_url: str = Field(
        default="redis://localhost:6379",
        validation_alias="REDIS_URL",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )


settings = Settings()
