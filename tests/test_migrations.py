from pathlib import Path

from pglast import parse_sql

ROOT = Path(__file__).parents[1]


def test_migrations_parse_as_postgresql() -> None:
    migrations = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
    assert migrations
    for migration in migrations:
        assert parse_sql(migration.read_text(encoding="utf-8")), migration.name


def test_public_tree_contains_no_private_installation_identifiers() -> None:
    forbidden = (
        "qhjbpvilm" + "szwqlozmqer",
        "reseau" + "-grolet",
        "169.58" + ".112.40",
        "michelgrolet" + "@gmail.com",
        "sb_publishable" + "_ZbWk",
    )
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or ".git" in path.parts
            or ".venv" in path.parts
            or "__pycache__" in path.parts
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert not any(secret in text for secret in forbidden), path
