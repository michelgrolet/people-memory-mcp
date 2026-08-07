import hashlib
import re
from pathlib import Path

from pglast import parse_sql

ROOT = Path(__file__).parents[1]

SKIPPED_DIRS = frozenset({".git", ".venv", "__pycache__", "node_modules", "dist"})

# Fingerprints (SHA-256) of the identifiers belonging to this installation: the Supabase project
# it runs against, its host, its owner. Hashes, not values — a guard that has to spell out what it
# protects turns the guard itself into the leak, which is exactly what this file used to do.
# Add one with:
#   python -c 'import hashlib,sys;print(hashlib.sha256(sys.argv[1].encode()).hexdigest())' VALUE
PRIVATE_FINGERPRINTS = frozenset(
    {
        "8c8acd2191f9ed43063827e9bae8abf981fa6a6c33fff41c795af7df828624c9",
        "b2c9e3ec6bac7874d2ec650f447aeb0cc1e51b00de40e2700e1d6a04d3ea7879",
        "a1f056e6cf18db3ebc4cdd472cfc93892dc5beb17543cfbbd9c989e33c2533e1",
        "16cfff0705b85ca47c5db04a206caa261bf95562d0658372a70e9d656a0ab788",
    }
)

# How a candidate identifier is carved out of a file. Dots split, so a project ref is still seen
# on its own inside a hostname; IPv4 addresses and e-mail addresses are matched whole.
TOKEN_PATTERNS = (
    re.compile(r"[A-Za-z0-9_-]{6,}"),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
)

# Shapes that are private whatever their value. These catch what nobody thought to fingerprint,
# including a key rotated after this list was written.
SECRET_SHAPES = (
    ("Supabase key", re.compile(r"sb_(?:publishable|secret)_[A-Za-z0-9_-]{4,}")),
    ("Supabase project URL", re.compile(r"https://[a-z]{20}\.supabase\.co")),
    # Local dev URLs (`…@127.0.0.1`) are documented in the README and are not credentials.
    (
        "remote PostgreSQL URL with a password",
        re.compile(r"postgres(?:ql)?://[^\s\"'/]+:[^\s\"'@]+@(?!127\.0\.0\.1|localhost|::1)"),
    ),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.")),
)


def _public_files():
    for path in ROOT.rglob("*"):
        if path.is_file() and not SKIPPED_DIRS.intersection(path.parts):
            yield path


def test_migrations_parse_as_postgresql() -> None:
    migrations = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
    assert migrations
    for migration in migrations:
        assert parse_sql(migration.read_text(encoding="utf-8")), migration.name


def test_public_tree_contains_no_private_installation_identifiers() -> None:
    for path in _public_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in TOKEN_PATTERNS:
            for token in pattern.findall(text):
                digest = hashlib.sha256(token.encode()).hexdigest()
                assert digest not in PRIVATE_FINGERPRINTS, (
                    f"{path.relative_to(ROOT)} contains a private installation identifier"
                )


def test_public_tree_contains_no_credential_shaped_strings() -> None:
    for path in _public_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in SECRET_SHAPES:
            match = pattern.search(text)
            assert match is None, f"{path.relative_to(ROOT)} looks like it contains a {label}"
