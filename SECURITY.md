# Security policy

## Report a vulnerability

Do not open a public issue for a vulnerability that could expose contact data or credentials.
Use GitHub's private vulnerability reporting for this repository.

## Supported version

Security fixes are applied to the latest release.

## Deployment rules

- Never put a PostgreSQL URL, database password, service-role key, OAuth secret, or API token in Git.
- Never use a Supabase service-role key in `web/config.js`.
- Keep forced row-level security enabled on every table used by the browser.
- Bind the optional API and MCP HTTP transport to loopback unless a real auth layer and TLS protect it.
- Restrict hosted signup after the owner account exists.
- Review connector permissions and use read-only scopes where possible.
- Back up the database before bulk imports, merges, or schema upgrades.

Agent instructions improve behavior but are not a security boundary. Database permissions, RLS,
network controls, and encryption must enforce the boundary mechanically.
