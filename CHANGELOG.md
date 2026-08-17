# Changelog

All notable changes to People Memory are documented here.

## [Unreleased]

### Added

- **Family tree view.** Clicking a person draws their bloodline: every ancestor and descendant, their
  brothers and sisters, and each of those spouses as a leaf. A spouse's own parents and siblings stay
  out, because drawing them puts two unrelated families on the same rows and claims a kinship that
  does not exist. Clicking a spouse re-roots the tree on their family. Generations are locked, so a
  child is always exactly one row under its parent and a couple always shares a row.
- **GEDCOM import**, with a review screen that will not create a second record for someone already in
  the graph. A genealogy export carries no email and no phone, so identity rests on name and birth
  date alone: a maiden name against a married name, a name that matches with a birth date that does
  not, or one name wanted by two records all stop and ask instead of guessing. Re-importing the same
  file creates nobody.
- **Merge screen.** Two records that might be the same person go side by side, the survivor editable
  field by field, with a window showing what the merged record becomes. Columns share their rows, so
  City sits opposite City.
- **Cleanup screen** for what the imports got wrong, every finding repairable from the panel. Two
  records sharing a name are told apart by their id in the confirmation.
- **Live LinkedIn sync** of first-degree connections through the Member Data Portability API, on top
  of the existing export importer.
- **Installable as a Claude Code plugin**, not only as a clone.
- **Progressive web app**: manifest, service worker, responsive layout, working back and swipe.
- **Expandable modal editor** with markdown rendering for text fields.
- **Organisation hierarchy**: a suborg hangs off its parent company and is pulled tight to it in the
  graph.
- **`people.kind`**, so an agent can be a node in the graph alongside people.
- **Partial dates.** A date you only half know is stored as what is actually known, `YYYY-MM` or
  `YYYY`, instead of being rejected or padded with a day nobody said.
- **Birthdays** read on Google Contacts import.
- **`⌘/`** opens a sheet listing every keyboard shortcut, grouped by where each key works.
- **Days spent with someone**, recorded on their record.
- Sync status and insights on the dashboard.

### Changed

- Relationship strength offers the three tiers actually used, named friend, close and closest.
- The MCP server reads its configuration before serving instead of on the first tool call. A missing
  or bad connection string now stops it with the reason, where the client logs it, rather than
  producing a server that starts and then fails every tool from inside the agent. `--help` and
  `--version` work.
- The README opens by answering the question people actually type.

### Fixed

- `resolve_person` asks for confirmation on a single fuzzy match. One candidate is not the same thing
  as the right candidate.
- Fact writes are idempotent and deduplicated, so the same fact recorded twice stays one row.
- New-person similarity no longer depends on schema grants, which made it behave differently on a
  hosted project than locally.
- A name shared by two records no longer links to whichever comes first. Same for an organisation
  name.
- The LinkedIn connection date is stored in the date column, not only as text.
- CI had never actually run, and applied only one migration when it did.
- **Identifiers are case-insensitive everywhere, not only on lookup.** Reading matched
  `lower(value)` while writing lowercased email alone, and the primary key is `(kind, value)`. So
  `linkedin.com/in/x` and `LinkedIn.com/in/X` were two rows `on conflict` could not see as one, and
  a person owning both came back as two candidates that nothing in the product could collapse again.
  Storage now agrees with lookup, the database carries the rule as a check constraint, and
  `20260817010000_identifiers_are_case_insensitive.sql` folds existing rows down. It stops rather
  than guess if a value differing only by case belongs to two different people; merge them first.
- The same profile URL in another case is no longer reported as a conflict by `remember_person`,
  which used to make it unanswerable for any importer that does not control casing.

### Security

- **The owner check fails closed.** `is_people_memory_owner()` compared two coalesced empty strings,
  so it returned true when both were absent: no owner row recorded, and a token carrying no email
  claim, which is what anonymous sign-in issues. Every policy in the schema is that one expression.
  Migration `20260817000000_owner_check_fails_closed.sql` fixes installations that already ran the
  earlier one.
- The login page no longer offers an email and password form when the API refuses that method, via a
  `passwordLogin` config flag.
- `search_path` pinned on every function.
- Test fixtures are invented people throughout, and `.claude/` is ignored so a local agent config
  cannot be committed.

## [0.1.0] - 2026-08-03

### Added

- A private PostgreSQL people graph with semantic MCP tools and optional guarded SQL.
- Local or hosted Supabase setup, forced single-owner RLS, a REST API, and a browser graph UI.
- Conservative LinkedIn, Google Contacts, and WhatsApp importers with ambiguity checks.
- Six agent skills for setup, durable memory, imports, enrichment, maintenance, and upgrades.
- Codex and Claude Code templates that retrieve people on mention and save durable facts.
- Automated Python, migration, privacy, packaging, plugin, and skill validation.
