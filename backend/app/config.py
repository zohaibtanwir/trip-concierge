"""Centralized env reading for the backend.

Reads `backend/.env` first, then process env (which wins). Importing
`settings` anywhere in `app/` is the only way to access config values
— don't `os.environ.get(...)` in route code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/trip_concierge",
        validation_alias="DATABASE_URL",
    )
    test_database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/trip_concierge_test",
        validation_alias="TEST_DATABASE_URL",
    )

    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    tavily_api_key: str = Field(default="", validation_alias="TAVILY_API_KEY")
    langfuse_public_key: str = Field(default="", validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", validation_alias="LANGFUSE_SECRET_KEY")

    # Used by the arq client in slice 2.5b's POST /trips/{id}/plan handler to
    # enqueue jobs. Worker side reads the same URL from agents/config.py.
    redis_url: str = Field(
        default="redis://localhost:6379",
        validation_alias="REDIS_URL",
    )

    # MCP token signing secret. Dev default is fine for local + CI; production
    # MUST override via TC_MCP_TOKEN_SECRET env. Compromise of this secret =
    # boot every active MCP session via rotation (the v1.0 revocation).
    tc_mcp_token_secret: str = Field(
        default="dev-only-do-not-use-in-prod",
        validation_alias="TC_MCP_TOKEN_SECRET",
    )

    # Shared secret between Next.js (web/) and FastAPI (backend/) for the
    # PWA → backend internal-RPC mint route added in slice 4.1. Different
    # trust root from TC_MCP_TOKEN_SECRET — compromise of this secret means
    # an attacker who reaches the backend network can mint MCP tokens for
    # arbitrary user_ids; rotation immediately closes the surface.
    internal_auth_secret: str = Field(
        default="dev-only-internal-auth-do-not-use-in-prod",
        validation_alias="INTERNAL_AUTH_SECRET",
    )

    # Resend send creds — slice 4.1b backend-side magic-link email for the
    # MCP challenge flow. SAME Resend account + from-address as slice 4.1's
    # web/Auth.js sends, but DIFFERENT subject + body so users can tell PWA
    # sign-in from MCP-challenge in their inbox.
    resend_api_key: str = Field(default="", validation_alias="RESEND_API_KEY")
    resend_from_email: str = Field(
        default="auth@tripconcierge.app",
        validation_alias="RESEND_FROM_EMAIL",
    )

    # Magic-link challenge TTL (slice 4.1b). 10 minutes is the spec-locked
    # window inherited from slice 4.1's RATE_LIMIT_POLL_PER_CODE = "1/2sec"
    # × 600s = 300-poll cap. Tighter than Auth.js's 24h verification_token
    # because MCP-challenge users are presumed to be at their keyboard.
    challenge_ttl_minutes: int = Field(default=10, validation_alias="CHALLENGE_TTL_MINUTES")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )


settings = Settings()
