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
    # Reachable only from the worker (ADR-005). Optional for the API process.
    sandbox_database_url: str = Field(
        "",
        description="libpq DSN for sandbox-db; required by the worker, unused by the API.",
    )
    # How long the orchestrator waits for the sandbox to finish one analysis.
    analysis_timeout_seconds: int = Field(300, ge=1)
    analysis_poll_seconds: int = Field(2, ge=1)

    # --- Operational tuning (seed defaults; the settings table overrides later, ADR-012) ---
    app_env: str = Field("local", description="Environment name for logs.")
    log_level: str = Field("INFO")

    # --- Artifact storage + upload limits (ADR-004c, untrusted-input defence) ---
    data_dir: str = Field("/data", description="Root for artifact/evidence storage.")
    max_upload_bytes: int = Field(300 * 1024 * 1024, ge=1)  # 300 MB
    max_uncompressed_bytes: int = Field(2 * 1024 * 1024 * 1024, ge=1)  # 2 GB zip-bomb ceiling
    max_zip_entries: int = Field(100_000, ge=1)

    # Leash defaults (ADR-011). These seed the settings table; they are not the
    # live source of truth once the settings table exists.
    max_agent_steps: int = Field(15, ge=1)
    max_active_requests: int = Field(30, ge=1)
    llm_step_timeout_seconds: int = Field(60, ge=1)
    tool_step_timeout_seconds: int = Field(30, ge=1)

    # Local-only posture (ADR-007): the browser origin allowed to call the API.
    allowed_origin: str = Field("http://127.0.0.1:8000")

    # --- Default scope for the "Run assessment" button (comma-separated lists). ---
    # SAFE default: the local lab hosts only. Set DEFAULT_ASSESS_HOSTS=* in your own .env
    # to authorize any host (operator responsibility; see ADR-016).
    default_assess_hosts: str = Field("lab-rest,firebase-lab,restapi-lab")
    default_assess_resources: str = Field("table:trips,table:invoices,table:profiles")
    default_active_testing: bool = Field(True)
    default_allow_lab_targets: bool = Field(True)

    def default_scope(self) -> dict:
        """Build the default assessment scope_configuration from env settings."""
        def _split(v: str) -> list[str]:
            return [x.strip() for x in v.split(",") if x.strip()]

        return {
            "active_testing_allowed": self.default_active_testing,
            "authorized_hosts": _split(self.default_assess_hosts),
            "authorized_resources": _split(self.default_assess_resources),
            "allow_lab_targets": self.default_allow_lab_targets,
            "max_active_requests": self.max_active_requests,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
