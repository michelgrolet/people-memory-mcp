# Deployment paths

## Hosted Supabase

Use a new personal project. Link the repo, run `supabase db push`, set `owner_email`, configure Auth,
and deploy `web/` to a static host. Put the publishable key in `web/config.js`. Store the direct DB URL
only in `~/.config/people-memory/.env`. Disable public signup after the owner account exists.

## Local Supabase

Require a Docker-compatible runtime and Supabase CLI. Run `supabase start` and `supabase db reset`.
Use the DB URL, API URL, publishable key, and Mailpit URL printed by `supabase status`. Never expose the
local stack to a public interface. Serve `web/` on loopback.

## Existing PostgreSQL

Apply only the core migration. Store the URL in the private env file. Use the optional token-protected
REST API for a browser or another application. Do not apply the Supabase RLS migration unless `auth.jwt()`
and the `authenticated`/`anon` roles exist.
