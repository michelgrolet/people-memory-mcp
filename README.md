# People Memory

**How do you give an AI agent persistent memory about people?** Point it at a real database instead
of a context window. People Memory is that database: an MCP server, a PostgreSQL schema, an optional
REST API, a browser UI, importers, and agent skills, all built around one graph of people, orgs, and
facts that survives every session. Add it once and Claude Code, Codex, or any other MCP client stops
forgetting who your mother-in-law is between conversations.

The server retrieves someone the moment you mention them, records durable facts as they come up, and
asks before it merges two people who might not be the same person. The graph, not the chat log, is
what remembers.

Your data stays in your own PostgreSQL database. The repository contains no hosted service, no
telemetry, no contact data, and no credentials.

## What it does

- Maps people, organizations, relationships, affiliations, identifiers, facts, and interactions.
- Gives Codex, Claude Code, and other MCP clients semantic tools plus guarded SQL.
- Teaches the agent to look up names before answering and save durable facts during every chat.
- Imports LinkedIn Connections, Google Contacts, WhatsApp chat exports, and GEDCOM family trees.
- Can enrich records through connectors the user approves, including Gmail, Calendar, and Drive.
- Runs fully local with Supabase CLI or in the cloud with any PostgreSQL database.
- Recommends a free Supabase project because it includes Postgres, Auth, REST, and a local stack.
- Includes a full-screen relationship graph and searchable directory.
- Flags what an import got wrong — duplicate people and organizations, contradictory links.
- Refuses uncertain merges and conflicting overwrites until the user decides.

## How it fits together

```mermaid
flowchart LR
  Agent["Your existing agent"] --> MCP["People Memory MCP"]
  MCP --> PG[("PostgreSQL")]
  Agent --> Connectors["Optional Gmail / Calendar / Drive / WhatsApp connectors"]
  Connectors --> MCP
  UI["Private graph UI"] --> Supabase["Supabase Auth + REST"]
  Supabase --> PG
  API["Optional REST API"] --> PG
```

The MCP server provides live reads and controlled writes. The bundled skills provide the behavior:
when to retrieve, what to remember, how to import, when to ask, and how to upgrade safely.

## Quick start

Requirements: Python 3.11+, [`uv`](https://docs.astral.sh/uv/), Docker, and the
[Supabase CLI](https://supabase.com/docs/guides/local-development).

```bash
git clone https://github.com/michelgrolet/people-memory-mcp.git
cd people-memory-mcp
uv sync --extra api --extra dev
supabase start
supabase db reset
```

`supabase status` prints the local database URL, API URL, and browser publishable key. Save the
database URL in `~/.config/people-memory/.env`:

```dotenv
PEOPLE_MEMORY_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
PEOPLE_MEMORY_ENABLE_RAW_SQL=false
PEOPLE_MEMORY_DEFAULT_SOURCE=agent
```

The file is read automatically and should have mode `0600`.

Set your owner email before using the UI:

```sql
update app_settings set value = 'you@example.com' where key = 'owner_email';
```

Then configure the browser app:

```bash
cp web/config.example.js web/config.js
# add the API URL and publishable key printed by `supabase status`
python3 -m http.server 4173 --directory web
```

Open [http://127.0.0.1:4173](http://127.0.0.1:4173). Local signup emails appear in Supabase
Mailpit, whose URL is also printed by `supabase status`.

## Connect an agent

The interactive wizard detects Codex and Claude Code:

```bash
uv run people-memory setup
```

Or add the server directly.

Codex:

```bash
codex mcp add people-memory \
  --env PEOPLE_MEMORY_ENV_FILE="$HOME/.config/people-memory/.env" \
  -- uvx --from git+https://github.com/michelgrolet/people-memory-mcp people-memory-mcp
```

Claude Code:

```bash
claude mcp add -s user people-memory \
  -e PEOPLE_MEMORY_ENV_FILE="$HOME/.config/people-memory/.env" \
  -- uvx --from git+https://github.com/michelgrolet/people-memory-mcp people-memory-mcp
```

Start a new agent session after adding an MCP server. Install or invoke `setup-people-memory` from
the plugin to add the durable memory rule, choose imports, connect optional data sources, and verify
the complete flow.

### With TARS, optionally

People Memory is standalone and stays standalone: nothing above requires a particular harness, and
the agent you already use is the one it wires into. [TARS](https://github.com/michelgrolet/tars) is
a harness for a personal agent that lists People Memory in its extension registry, so if you happen
to run it, one command does the clone and the wiring:

```bash
claude plugin marketplace add michelgrolet/tars
claude plugin install people-memory@tars
```

What that adds over the plain MCP server is when the tools fire: TARS puts the trigger in the one
file it loads on every session, so the agent looks a person up before answering instead of waiting
to be told to. Without it, the `remember-people` skill does the same job once you install it.

### Install the agent skills from a clone

Codex discovers skills in `~/.agents/skills`; Claude Code uses `~/.claude/skills`. Symlink every
People Memory skill so updates to the clone are picked up automatically:

```bash
mkdir -p "$HOME/.agents/skills"
for skill in "$PWD"/skills/*; do
  ln -s "$skill" "$HOME/.agents/skills/$(basename "$skill")"
done
```

Use `~/.claude/skills` instead for Claude Code. Restart the agent, then ask it to run
`setup-people-memory`. The repository is also packaged as a Codex plugin for marketplace or team
distribution.

## MCP tools

| Tool | Purpose |
|---|---|
| `search_people` | Search names, organizations, roles, cities, identifiers, summaries, and facts |
| `get_person` | Return a complete person record, or candidates when a name is ambiguous |
| `remember_person` | Create or update a person without silent duplicate merges or overwrites |
| `add_fact` | Save typed or free-form facts with source and confidence |
| `record_interaction` | Record a call, message, meeting, meal, or other dated interaction |
| `connect_people` | Record how two people know each other |
| `find_intro_path` | Find warm introduction paths into an organization |
| `stale_contacts` | Find strong relationships that have gone quiet |
| `read_query` | Run one guarded `SELECT` for advanced analysis |
| `write_query` | Run one guarded `INSERT`, `UPDATE`, or `DELETE` |

Raw SQL is disabled by default. If enabled, the parser rejects multiple statements, DDL, a short
list of dangerous functions, `SELECT ... INTO`, more than one data-changing operation, and
`UPDATE`/`DELETE` with no `WHERE` clause.

That parser is a denylist, so treat it as the first of two layers rather than the guarantee. The
guarantee is underneath it: `read_query` runs in a transaction with `default_transaction_read_only`
on, a 30-second statement timeout and a bounded result set, so a `SELECT` that finds a way past the
parser still cannot write. Both tools stay behind `PEOPLE_MEMORY_ENABLE_RAW_SQL`, and RLS applies to
them exactly as it does to everything else.

## Imports

Official exports are the safest default. They are inspectable and do not require sharing account
passwords.

```bash
uv run people-memory import linkedin ~/Downloads/Connections.csv
uv run people-memory import google ~/Downloads/contacts.csv
uv run people-memory import whatsapp ~/Downloads/chat.txt --self-name "Your Name" --date-order dmy
```

Imports resolve email or phone first, then name. They fill missing values and never overwrite a
conflict silently. The `import-contacts` skill can inspect unfamiliar CSV columns and guide the user
through ambiguous matches.

### Family trees (GEDCOM)

A genealogy export carries something no contact export has: who is whose parent, who married whom,
and who the siblings are. Open the web app, click the upload button in the header, and drop a `.ged`
file from Geneanet, Ancestry, MyHeritage or Gramps.

A GEDCOM has no email and no phone, so the dedup key the other importers rely on does not exist:
identity is resolved on name and birth date, and a woman recorded under her maiden name is also
matched against her spouses' surnames. Anything those cannot settle — the same name on two records,
a birth date that contradicts a name match, two entries in the file that may be one person — is
listed on a review screen and nothing is written until every one of them is answered. Rerunning the
same file writes nothing the second time.

What lands: a person per individual (full birth dates in the column, partial or hedged ones as a
`born` fact), `parent` / `partner` / `sibling` links, and `birth_place`, `died`, `death_place`,
`occupation` facts. A link that already exists is left untouched, notes included.

### LinkedIn, live

LinkedIn also exposes 1st-degree connections live through its Member Data Portability API (DMA).
Once you hold an OAuth token with the `r_dma_portability_self_serve` scope (see
[LinkedIn's docs](https://learn.microsoft.com/en-us/linkedin/dma/member-data-portability/member-data-portability-member/)),
you can sync without the manual export. Set the token as an environment variable — never pass it
as a CLI flag, which would leak it through `ps` and shell history:

```bash
export LINKEDIN_OAUTH_TOKEN="..."
uv run people-memory sync-linkedin
```

Right after consenting, LinkedIn may not have collated the `CONNECTIONS` domain yet — it raises a
readable error in that case; retry later or fall back to the CSV export above.

## Optional connectors

People Memory does not collect Gmail, Calendar, Drive, or WhatsApp credentials. The `enrich-people`
skill uses connectors already authorized in the user's agent. It asks which sources may be read,
limits the time range, shows what it plans to save, and marks every fact with its source.

Supported patterns include:

- Gmail: participants, signatures, organizations, and last interaction dates.
- Calendar: meetings, attendees, locations, and interaction dates.
- Drive: user-selected documents that mention known people.
- WhatsApp: official exports by default; a self-hosted MCP bridge is optional.
- Browser agents: Codex in Chrome or Claude in Chrome can help configure Supabase and inspect the UI.

See [docs/connectors.md](docs/connectors.md) for the permission and identity rules.

### Cleanup

Every import writes records nobody reads again, and they collide. The shield button in the top bar
opens a screen that reads them for you: two records sharing an email or a phone, the same name
spelled two ways, an organization entered twice under a legal suffix, an organization nobody
belongs to, links that cannot all be true (someone their own ancestor, a parent younger than their
child, a pair filed as both parent and sibling), and family links still too vague for the tree.
The count on the button is what is waiting.

It never decides anything, but every finding is repairable from the panel. Duplicate-looking records
are routinely two real people — a son named after his father, three sisters given the same name — so
each finding shows the records side by side with what separates them, and a pair already linked to
each other is left out entirely: the link is somebody having decided they differ, and a merge across
a `parent`, `sibling` or `partner` link is refused by the database itself.

**Merge** opens a window with both records on the outside and the one they are about to become in
the middle. The middle follows the same rules the server does — the survivor keeps its own values,
inherits whatever it lacks, takes the closer of the two ratings, keeps both notes — and every field
in it is editable, because the right answer is often one record's name and the other's job, which
picking a winner cannot express. Clicking a value on either side takes it. Which record survives is
a toggle, and switching it leaves whatever you typed alone. Nothing is written until you confirm.

An empty organization is deleted in a click; a family link nobody classified is filed as parent,
child, sibling or partner in a click, keeping the note that was on it; a parent link pointing at
someone born before their own child is flipped in a click. **Not a problem** hides a finding for
good, stored with the owner's own settings so the list drains instead of nagging.

A merge moves rows across five tables, so it runs as one Postgres function rather than a series of
calls from the browser: it cannot stop halfway and leave a record whose facts moved but whose links
did not. The losing record is archived into `deleted_records` in full — with the id it was merged
into — before anything moves, so every merge is recoverable.

### Shared days, if you also keep a location archive

Off by default. Set `locationCompanions: true` in `web/config.js` when the same database also
carries the schema from [tars-location-mcp](https://github.com/michelgrolet/tars-location-mcp).
The record card then gets a **With me** block: give a person a date range, times optional, and
the location archive answers where the two of you were — cities, countries, and the trip it
falls in. Nothing is typed twice, and nothing about a place is stored on the person.

People Memory owns none of those tables. With the flag off, or with the tables absent, the
block does not render and the app loads exactly as before.

## Hosted Supabase

Create a free Supabase project, then apply the checked-in migrations:

```bash
supabase login
supabase link --project-ref YOUR_PROJECT_REF
supabase db push
```

Set `owner_email`, enable the desired Auth providers, and deploy `web/` to a static host. The browser
uses only the publishable key. Row-level security rejects every account except the configured owner.
The MCP server uses a direct PostgreSQL URL stored outside Git.

For an existing non-Supabase PostgreSQL database, apply every file in `supabase/migrations/` in
filename order and use the optional API for browser access:

```bash
for f in supabase/migrations/*.sql; do psql "$PEOPLE_MEMORY_DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"; done
```

`20260803000100_security.sql` expects the Supabase `anon`/`authenticated` roles and an `auth.jwt()`
function; outside Supabase, create them first or skip that file and keep the database private.
Upgrading an existing install means applying the migrations it has not seen yet, in the same order.

## Optional REST API

```bash
uv run --extra api people-memory api --host 127.0.0.1 --port 8765
```

Set `PEOPLE_MEMORY_API_TOKEN` to require `Authorization: Bearer ...`. Keep the API on loopback unless
you put it behind TLS, authentication, rate limits, and backups.

## Skills

- `setup-people-memory`: choose local/cloud deployment, configure an existing agent, select imports,
  offer approved connectors, start the UI, and verify the install.
- `remember-people`: retrieve on name mention and save durable human facts during conversation.
- `import-contacts`: import and deduplicate official exports.
- `enrich-people`: use approved Gmail, Calendar, Drive, browser, or WhatsApp connectors.
- `maintain-people-memory`: audit duplicates, conflicts, stale ties, and data quality.
- `upgrade-people-memory`: back up, migrate, upgrade the MCP/UI/skills, and verify data.

If the user does not already have an agent, the setup skill can create a minimal Codex or Claude Code
workspace from `templates/` and connect People Memory to it.

## Privacy and safety

This database contains third-party personal data. Treat it accordingly.

- One database per person is the default design.
- Hosted UI access is restricted with Supabase Auth and forced row-level security.
- The browser publishable key is safe to expose only because RLS is enabled.
- The service-role key and PostgreSQL password must never enter browser code or Git.
- Connector access is opt-in per source. Imported and inferred facts keep provenance.
- Delete archives a JSON snapshot in `deleted_records` before cascading dependent rows.
- Back up before schema upgrades or bulk merges.

Read [docs/privacy.md](docs/privacy.md) and [SECURITY.md](SECURITY.md) before exposing any component
to the internet.

## Development

```bash
uv sync --extra api --extra dev
uv run ruff check .
uv run pytest --cov=people_memory
supabase db reset
```

The project uses the current stable v2 line of the official
[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) and the latest Supabase migration
workflow.

## License

[MIT](LICENSE)
