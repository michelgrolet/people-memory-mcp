from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ENV_PATH = Path.home() / ".config" / "people-memory" / ".env"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_token: str | None
    enable_raw_sql: bool
    default_source: str
    cors_origins: tuple[str, ...]

    @classmethod
    def load(cls) -> Settings:
        configured = os.environ.get("PEOPLE_MEMORY_ENV_FILE")
        env_path = Path(configured).expanduser() if configured else DEFAULT_ENV_PATH
        file_values = _read_env_file(env_path)

        def value(key: str, default: str = "") -> str:
            return os.environ.get(key, file_values.get(key, default))

        database_url = value("PEOPLE_MEMORY_DATABASE_URL") or value("DATABASE_URL")
        if not database_url:
            raise RuntimeError(
                "PEOPLE_MEMORY_DATABASE_URL is missing. Run `people-memory setup` or set it "
                f"in {env_path}."
            )
        origins = tuple(
            item.strip()
            for item in value(
                "PEOPLE_MEMORY_CORS_ORIGINS",
                "http://127.0.0.1:4173,http://localhost:4173",
            ).split(",")
            if item.strip()
        )
        return cls(
            database_url=database_url,
            api_token=value("PEOPLE_MEMORY_API_TOKEN") or None,
            enable_raw_sql=_truthy(value("PEOPLE_MEMORY_ENABLE_RAW_SQL", "false"), False),
            default_source=value("PEOPLE_MEMORY_DEFAULT_SOURCE", "agent") or "agent",
            cors_origins=origins,
        )
