---
name: upgrade-people-memory
description: Upgrade an installed People Memory plugin, MCP package, PostgreSQL/Supabase schema, optional API, web UI, and bundled skills; inspect release notes, back up data, apply ordered migrations, refresh uvx or local installs, preserve config and credentials, restart agents, and verify reads and writes. Use when the user says upgrade, update, migrate, install the latest release, schema migration, refresh the plugin, or repair a version mismatch.
---

# Upgrade People Memory

Keep the database recoverable and configuration private.

## Preflight

1. Call `graph_status` and record counts.
2. Identify the installed package, plugin, schema migration level, and UI version.
3. Read release notes from the current version through the target version.
4. Flag breaking changes, new connector permissions, or required user choices before mutation.

## Back up

Create a timestamped `pg_dump` in a private location. Verify the file is non-empty and record the
restore command. Do not put the backup in Git or an agent artifact store.

## Upgrade

1. Pull or install the target release.
2. Apply pending Supabase migrations in order. Never run `db reset` against a linked production
   project.
3. Refresh the `uvx` package cache or local virtual environment.
4. Update plugin skills and MCP config without overwriting the user's environment file.
5. Rebuild or redeploy the static UI when its files changed.
6. Start a new agent session so MCP and skill changes load.

## Verify

1. Call `graph_status` and compare counts.
2. Read a known synthetic or user-approved test record.
3. Create, retrieve, update, and archive-delete a synthetic record.
4. Verify login, search, edit, and graph rendering in the UI.
5. Remove the synthetic record and archive.

If a check fails, stop writes, preserve logs without contact data, and offer the tested restore path.
Finish with old/new versions, migrations applied, verification results, and any manual login still
needed. Do not print secrets or database URLs.
