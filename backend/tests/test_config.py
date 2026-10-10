"""Config must fail loudly when the required DSN is missing or empty."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_missing_dsn_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAIN_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_empty_dsn_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIN_DATABASE_URL", "")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_valid_dsn_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIN_DATABASE_URL", "postgresql://u:p@db:5432/x")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.main_database_url.endswith("/x")
    assert s.max_agent_steps == 15  # leash default (ADR-011)
