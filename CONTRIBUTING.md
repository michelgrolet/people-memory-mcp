# Contributing

Issues and pull requests are welcome.

## Setup

```bash
uv sync --extra api --extra dev
supabase start
supabase db reset
```

## Checks

```bash
uv run ruff check .
uv run pytest --cov=people_memory
python3 /path/to/skill-creator/scripts/quick_validate.py skills/setup-people-memory
```

Run the skill validator for every directory under `skills/`. Validate the plugin manifest with the
OpenAI plugin validator before changing `.codex-plugin/plugin.json` or `.mcp.json`.

## Data rule

Fixtures, screenshots, logs, issues, and pull requests must contain synthetic people only. Never add
real contact exports or production database dumps.
