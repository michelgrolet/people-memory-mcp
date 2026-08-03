from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from .config import Settings


class Database:
    """Small connection wrapper. Each MCP call gets a short-lived connection."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @contextmanager
    def connection(self) -> Iterator[Connection[dict[str, Any]]]:
        with psycopg.connect(
            self.settings.database_url,
            row_factory=dict_row,
            autocommit=True,
            connect_timeout=20,
            application_name="people-memory",
        ) as conn:
            conn.execute("set statement_timeout = '30s'")
            yield conn

    @contextmanager
    def transaction(self) -> Iterator[Connection[dict[str, Any]]]:
        with psycopg.connect(
            self.settings.database_url,
            row_factory=dict_row,
            autocommit=False,
            connect_timeout=20,
            application_name="people-memory",
        ) as conn:
            conn.execute("set statement_timeout = '30s'")
            with conn.transaction():
                yield conn

    def fetch_all(self, query: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            return list(conn.execute(query, params or ()).fetchall())

    def fetch_one(self, query: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
        with self.connection() as conn:
            return conn.execute(query, params or ()).fetchone()

    def fetch_read_only(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Run an advanced query in a read-only transaction and bound client memory."""
        with psycopg.connect(
            self.settings.database_url,
            row_factory=dict_row,
            autocommit=False,
            connect_timeout=20,
            application_name="people-memory-read-only",
            options="-c default_transaction_read_only=on -c statement_timeout=30000",
        ) as conn:
            cursor = conn.execute(query)
            return list(cursor.fetchmany(limit))
