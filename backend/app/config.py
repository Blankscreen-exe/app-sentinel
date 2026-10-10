"""Configuration, loaded from the environment.

Fails loudly at startup when a required value is missing, rather than failing
later in an obscure place (foundation acceptance criterion 7).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Required: no sensible default, startup must fail if absent ---
    main_database_url: str = Field(
        ...,
        min_length=1,
        description="SQLAlchemy/psycopg DSN for the main database.",
    )

    # --- Operational tuning (seed defaults; the settings table overrides later, ADR-012) ---
    app_env: str = Field("local", description="Environment name for logs.")
    log_level: str = Field("INFO")

    # Leash defaults (ADR-011). These seed the settings table; they are not the
    # live source of truth once the settings table exists.
    max_agent_steps: int = Field(15, ge=1)
    max_active_requests: int = Field(30, ge=1)
    llm_step_timeout_seconds: int = Field(60, ge=1)
    tool_step_timeout_seconds: int = Field(30, ge=1)

    # Local-only posture (ADR-007): the browser origin allowed to call the API.
    allowed_origin: str = Field("http://127.0.0.1:8000")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
