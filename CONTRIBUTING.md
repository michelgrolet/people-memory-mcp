# Contributing

Issues and pull requests are welcome.

## Setup

```bash
uv sync --extra api --extra dev
supabase start
supabase db reset
```

## Checks

These are exactly what CI runs, so a green run here is a green run there.

```bash
uv run ruff check .
uv run pytest --cov=people_memory --cov-report=term-missing
node --test web/tests/*.test.mjs
```

The database tests skip themselves when they have nowhere to connect, so `pytest` goes green having
tested no database behaviour at all. Set `PEOPLE_MEMORY_TEST_DATABASE_URL` to the `DB URL` that
`supabase start` printed, then run the same command again and watch the skips turn into passes.
That port is `54322` unless you changed it in `supabase/config.toml`.

CI runs those tests against a throwaway Postgres 17 on every push, so a pull request that only ever
ran them skipped will still be checked. Running them locally is how you find out before the push.

The dashboard is one `index.html` with no build step, so `node --test` covers the pieces that can
be tested without a browser: the markdown renderer, the GEDCOM parser and matcher, the family-tree
layout, and the name pickers.

## Data rule

Fixtures, screenshots, logs, issues, and pull requests must contain synthetic people only. Never add
real contact exports or production database dumps. Invented names in the existing fixtures look like
`Wren Halloway`, `Alder Brennick` and `Halloway & Sons`; follow that register rather than reaching
for someone you know.
