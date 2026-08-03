---
name: remember-people
description: >-
  Use People Memory automatically during ordinary conversation: retrieve a person's record whenever
  the user mentions them, remember durable facts about humans, record calls or meetings, update jobs
  or cities, connect people, and answer who the user knows. Trigger on any named person, durable human
  fact, relationship, affiliation, interaction, warm-introduction question, stale-contact question,
  or request to recall who someone is. Do not use for facts about the user themself unless they
  explicitly model them as a person in the graph.
---

# Remember people

Use the `people-memory` MCP as the durable human memory behind the conversation.

## On every name mention

1. Call `search_people` before answering.
2. If one record matches, use it silently as context.
3. If several records match and the answer depends on identity, ask which person the user means.
4. If no record matches, continue the conversation. Create the person when the user provides a
   durable fact or explicitly says they know them.

Do not ask “who is that?” until the graph search has failed.

## Save durable facts

Write facts that should survive the current chat, including:

- job, organization, role, city, country, birthday, family, preferences, goals, or constraints;
- how two people know each other;
- who introduced whom;
- a dated call, meeting, message, coffee, meal, or visit;
- a new email, phone, LinkedIn URL, or other stable identifier.

Use `remember_person` for core fields and one simple fact. Use `add_fact`, `record_interaction`, and
`connect_people` for their specific records. Save the source and mark deductions as `inferred`.

Do not store passing jokes, guesses, judgments, full message bodies, or facts about the user's inner
life. Keep compact facts that help a future conversation.

## Resolve before writing

Resolve by email or phone, then exact name. If a tool returns `needs_confirmation`, ask the user and
retry with `confirmed_new=true` or `overwrite=true` only after they decide. Never silently merge
similar names. Never replace a user-stated value with imported or inferred data.

## Answer network questions

- Use `get_person` for “who is X?”
- Use `search_people` for organization, role, city, or free-text questions.
- Use `find_intro_path` for warm introductions.
- Use `stale_contacts` for neglected relationships.
- Use `read_query` for advanced filters that semantic tools do not cover.

Treat returned records as private third-party data. Do not quote or export them to anyone except the
user who owns the graph.
