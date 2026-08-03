# Repository instructions

- Use only synthetic people in tests, docs, screenshots, logs, and commits.
- Keep all credentials out of Git. Browser code may receive a Supabase publishable key, never a
  service-role key or PostgreSQL password.
- Preserve source and confidence on imported or inferred facts.
- Never merge ambiguous identities automatically.
- Run `uv run ruff check .` and `uv run pytest` after Python changes.
- Run `supabase db reset` after migration changes.
- Validate every changed skill and the plugin manifest before release.
