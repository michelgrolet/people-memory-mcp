from people_memory.config import Settings


def test_raw_sql_is_disabled_by_default(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PEOPLE_MEMORY_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("PEOPLE_MEMORY_DATABASE_URL", "postgresql://example.invalid/db")
    monkeypatch.delenv("PEOPLE_MEMORY_ENABLE_RAW_SQL", raising=False)

    assert Settings.load().enable_raw_sql is False
