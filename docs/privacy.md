# Privacy model

People Memory is designed as a personal, single-owner database. The data describes third parties,
so privacy has to hold even when the agent makes a bad decision.

## Boundaries

- The database is the only durable copy created by the application.
- Agent instructions control workflow, not access. PostgreSQL roles and Supabase RLS control access.
- The hosted browser authenticates through Supabase Auth. Only the email in `app_settings.owner_email`
  passes `is_people_memory_owner()`.
- The MCP server receives a direct database URL from a private environment file.
- The optional API uses a bearer token when `PEOPLE_MEMORY_API_TOKEN` is set.

## Provenance

Every identifier, affiliation, relationship, fact, and interaction carries a source. Facts also carry
`stated`, `observed`, or `inferred` confidence. An import fills gaps and surfaces conflicts. It does
not silently replace something the user stated.

## Connectors

The plugin never stores OAuth tokens. Enrichment skills use connectors already authorized by the
agent host. The user chooses the source and time range before reading. The agent should save the
minimum useful fact, not full emails, chat bodies, documents, or calendar descriptions.

## Deletion and backups

`delete_person()` archives a JSON snapshot before cascading dependent records. This makes accidental
UI deletion recoverable, but it is not a legal erasure until the archive and backups are also purged.

For a complete erasure request:

1. Delete the live person record.
2. Delete matching rows from `deleted_records`.
3. Rotate or expire backups containing the record.
4. Delete raw import files and connector caches.
