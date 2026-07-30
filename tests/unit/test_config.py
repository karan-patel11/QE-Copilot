"""T2 PASS: settings load from env and build correct connection URLs."""

from __future__ import annotations

from qe_common.config import Settings


def test_defaults_and_urls() -> None:
    s = Settings()
    assert s.service_name == "qe-copilot"
    assert s.database_url.startswith("postgresql+psycopg://")
    assert s.async_database_url == s.database_url
    assert s.redis_url.startswith("redis://")


def test_env_override(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("POSTGRES_HOST", "db.example.com")
    monkeypatch.setenv("POSTGRES_DB", "custom")
    s = Settings()
    assert "db.example.com" in s.database_url
    assert s.database_url.endswith("/custom")
