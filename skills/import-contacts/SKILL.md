---
name: import-contacts
description: Import people into People Memory with built-in LinkedIn Connections CSV, Google Contacts CSV, and WhatsApp export support, or an agent-reviewed mapping for vCards and arbitrary CSV/JSON; preview fields, normalize identifiers, deduplicate, surface ambiguous identities and conflicting values, and report results. Use when the user says import, migrate, seed, sync, deduplicate, merge contacts, LinkedIn, Google Contacts, WhatsApp export, address book, vCard, or contact CSV.
---

# Import contacts

Import official exports conservatively. Preserve source, keep existing stated values, and stop on
identity ambiguity.

## Workflow

1. Identify the source and inspect headers or a small sample. Never print private rows in full.
2. Read [references/formats.md](references/formats.md) for that source only.
3. Preview the record count, fields found, identifiers available, and fields that will be ignored.
4. Ask the user whether to proceed when the export includes sensitive fields they did not request.
5. Run the matching `people-memory import` command. For other formats, show the mapping and use
   `remember_person` only after approval.
6. Report created, updated, ambiguous, conflicting, and skipped counts.
7. Run the duplicate and orphan checks from `maintain-people-memory`.

## Identity order

Resolve in this order:

1. normalized email;
2. normalized phone;
3. LinkedIn URL or source-native stable identifier;
4. exact normalized full name;
5. similar name only as a candidate requiring the user's decision.

Do not auto-merge two people because their names are similar. Do not auto-create a similar name when
the source lacks an identifier. Ask whether it is the existing person or someone new.

## Write rules

- Fill empty fields from imports.
- Keep an existing value when the import conflicts.
- Surface the conflict with existing and incoming values.
- Save source-specific dates as observed facts or interactions.
- Keep raw export files outside Git and delete them when the user no longer needs them.
- Never upload contact exports to an external model or service without explicit approval.

For an unfamiliar CSV, infer a proposed mapping, show it, and ask before writing. Prefer a reusable
mapping file or importer change when the format will recur.
