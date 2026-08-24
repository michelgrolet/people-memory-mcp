"""Every table in `public` is owner-only, and stays that way when a new one is added.

`20260803000100_security.sql` locks the nine tables that existed when it was written, then sets
`alter default privileges in schema public grant select, insert, update, delete on tables to
authenticated`. Those two facts together mean a table created by any later migration arrives
already granted to `authenticated` and with no policy on it — open, by default, silently.
`org_aliases` took exactly that path. Reviewing the next migration is not a guard; this is.
"""

import os

import pytest

from people_memory.config import Settings
from people_memory.db import Database

pytestmark = pytest.mark.integration


@pytest.fixture
def conn():
    url = os.environ.get("PEOPLE_MEMORY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("PEOPLE_MEMORY_TEST_DATABASE_URL is not set")
    database = Database(
        Settings(
            database_url=url,
            api_token=None,
            enable_raw_sql=True,
            default_source="test",
            cors_origins=(),
        )
    )
    with database.connection() as connection:
        yield connection


def _public_tables(conn) -> list[str]:
    rows = conn.execute(
        """
        select c.relname as name
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r'
        order by c.relname
        """
    ).fetchall()
    return [row["name"] for row in rows]


def test_every_public_table_has_row_level_security_enabled_and_forced(conn) -> None:
    # `force` and not only `enable`: the migrations run as the table owner, and an owner is exempt
    # from its own policies unless the table forces them.
    rows = conn.execute(
        """
        select c.relname as name, c.relrowsecurity as enabled, c.relforcerowsecurity as forced
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r'
        order by c.relname
        """
    ).fetchall()
    assert rows, "no tables found — the migrations did not apply"
    unprotected = [r["name"] for r in rows if not (r["enabled"] and r["forced"])]
    assert not unprotected, (
        f"tables without forced row level security: {unprotected}. "
        "A new table inherits the `authenticated` grant from the security migration's default "
        "privileges, so leaving RLS off makes it world-readable to any signed-in role."
    )


def test_every_public_table_is_owner_only(conn) -> None:
    tables = _public_tables(conn)
    policies = conn.execute(
        """
        select tablename as name, policyname, roles::text as roles, cmd, qual, with_check
        from pg_policies
        where schemaname = 'public'
        """
    ).fetchall()
    by_table = {row["name"]: row for row in policies if row["policyname"] == "owner_only"}
    missing = [name for name in tables if name not in by_table]
    assert not missing, f"tables with no owner_only policy: {missing}"
    for name, policy in by_table.items():
        assert policy["cmd"] == "ALL", name
        assert "authenticated" in policy["roles"], name
        assert "is_people_memory_owner()" in (policy["qual"] or ""), name
        assert "is_people_memory_owner()" in (policy["with_check"] or ""), name


def test_anon_holds_no_privilege_on_any_public_table(conn) -> None:
    # `anon` is the role an unauthenticated PostgREST request runs as. It must not reach a table
    # at all — RLS is the second line, not the first.
    rows = conn.execute(
        """
        select table_name as name, privilege_type as privilege
        from information_schema.role_table_grants
        where table_schema = 'public' and grantee = 'anon'
        order by table_name, privilege_type
        """
    ).fetchall()
    assert not rows, f"anon can reach: {[(r['name'], r['privilege']) for r in rows]}"
