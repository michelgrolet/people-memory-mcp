---
name: maintain-people-memory
description: >-
  Audit and maintain a People Memory graph: find probable duplicate people or organizations, orphan
  records, conflicting facts, missing identifiers, stale relationships, invalid dates, import
  quality issues, or oversized archives; propose merges and cleanup, back up first, and apply only
  user-approved destructive changes. Use for doctor, audit, cleanup, dedupe, merge, stale contacts,
  graph health, data quality, restore, or repair requests.
---

# Maintain People Memory

Start read-only. Show evidence for each proposed change.

## Audit

1. Call `graph_status`.
2. Use guarded SQL to find exact normalized duplicate names and organizations.
3. Search similar names only as candidates, never as automatic duplicates.
4. Find people without identifiers, affiliations pointing to deleted history mistakes, facts without
   useful provenance, invalid dates, self-edges, and conflicting current affiliations.
5. Call `stale_contacts` separately. Staleness is a relationship prompt, not a data defect.
6. Check `deleted_records` size and backup age.

Group findings into safe automatic fixes, identity decisions, destructive cleanup, and suggestions.

## Change gate

Ask before merges, deletes, archive purges, provenance changes, or bulk updates. Back up the database
before approved destructive work. Use a transaction and verify row counts before commit.

When merging people, choose a survivor with the strongest identifiers and most user-stated data.
Move identifiers, affiliations, facts, interactions, and both sides of relationships. Resolve unique
key conflicts explicitly. Archive both pre-merge records. Delete the duplicate last.

## Verify

Re-run the audit, read the survivor record, and verify the UI search. Report exactly what changed and
what remains unresolved. Do not expose third-party data beyond the minimum needed for the owner's
decision.
