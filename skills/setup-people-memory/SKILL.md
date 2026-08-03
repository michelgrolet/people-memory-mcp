---
name: setup-people-memory
description: Set up or reconfigure People Memory for an existing Codex, Claude Code, Cursor, or other MCP-capable agent; create a minimal personal agent if needed; choose local PostgreSQL or hosted Supabase; install the schema, MCP, UI, and durable memory instructions; ask which LinkedIn, Google Contacts, WhatsApp, Gmail, Calendar, Drive, or browser connections the user wants. Use for first install, moving between local and cloud, adding an agent, or repairing an incomplete People Memory setup.
---

# Set up People Memory

Configure the whole path from conversation to private database. Keep credentials out of chat output,
Git, browser code, and shell history where possible.

## 1. Inspect before asking

1. Check whether the `people-memory` MCP tools are already present.
2. If present, call `graph_status`. Offer repair or reconfiguration instead of reinstalling blindly.
3. Detect the current agent, `uv`, Supabase CLI, Docker-compatible runtime, and browser tools.
4. Locate a cloned `people-memory-mcp` repo if one exists.

Do not claim a component works because its config file exists. Verify the MCP with `graph_status`.

## 2. Ask the deployment choice

Ask one compact question with these options:

- Hosted Supabase, recommended for a free cloud backend, Auth, REST, and browser UI.
- Local Supabase, recommended when all contact data must remain on the machine.
- Existing PostgreSQL, for users who already operate a database. Explain that the UI then needs the
  optional API or a compatible auth/REST layer.

Read [references/deployment.md](references/deployment.md) for the chosen path. Do not load the other
paths.

## 3. Set the owner and secrets

1. Store the PostgreSQL URL in `~/.config/people-memory/.env` with mode `0600`.
2. Generate an API token if the optional REST API will run.
3. Set `app_settings.owner_email` to the account that may open the hosted UI.
4. Put only the Supabase URL and publishable key in `web/config.js`.
5. Never put a service-role key or PostgreSQL URL in the browser.

## 4. Connect the current agent

Prefer the user's existing agent. Add the stdio MCP through that agent's supported command or config.
For Codex and Claude Code, use the exact current commands in the repository README. Start a fresh
session after changing MCP config.

Offer to install the durable memory rule from `templates/AGENTS.md` or `templates/CLAUDE.md`. Ask
before changing a global user instruction file. Preserve existing content and add one clearly named
section.

If the user has no agent, offer a minimal workspace containing the matching template and connect it
to Codex or Claude Code. Do not build a custom agent runtime unless they ask for one.

## 5. Ask what to import

Ask which sources the user wants now:

- LinkedIn Connections export
- Google Contacts CSV
- WhatsApp chat export
- Another CSV for agent-guided column mapping
- Nothing yet

Invoke `import-contacts` for selected sources. Prefer official exports before live account access.

## 6. Offer optional live connectors

Ask whether the user wants to connect Gmail, Calendar, Drive, or a live WhatsApp bridge. State what
each source would reveal. Use an already-authorized connector when available. Otherwise help the user
connect one, but never request passwords in chat.

Offer Codex in Chrome or Claude in Chrome when available for visible Supabase setup and graph UI
verification. Let the user watch and take over for login or credential entry.

Invoke `enrich-people` only for sources the user approves.

## 7. Start and verify

1. Apply migrations.
2. Start the UI locally or deploy `web/` to the selected static host.
3. Call `graph_status` in a fresh agent session.
4. Create a synthetic test person, read it back, and delete it through `delete_person` or guarded SQL.
5. Open the UI and verify login, search, create, edit, and archived deletion.
6. Remove the synthetic record and its archive.

Finish with the chosen deployment, connected agents, enabled imports/connectors, UI address, and any
step that still needs the user's login. Do not print secrets.
