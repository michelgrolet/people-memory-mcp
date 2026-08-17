-- `is_people_memory_owner()` compared two coalesced empty strings:
--
--   coalesce(auth.jwt() ->> 'email', '') = coalesce((select value from app_settings ...), '')
--
-- so it returned TRUE whenever both sides were absent — no `owner_email` row in `app_settings`,
-- and a token carrying no `email` claim. Supabase's `signInAnonymously()` issues exactly that
-- token: role `authenticated`, no email. On an installation whose owner row was never written,
-- or was cleared, or was renamed, anonymous sign-in therefore passed every policy on every table,
-- read and write. The only thing standing in the way was the seeded `owner@example.com` default,
-- which is a coincidence rather than a control.
--
-- Every policy in this schema is `using (is_people_memory_owner())`, so this one expression is the
-- whole boundary. It now fails closed: no email on the token, or no owner recorded, and nobody is
-- the owner.
--
-- Fixed at the source in 20260803000100_security.sql as well, so a fresh install never has it.
-- This migration exists for the installations that already ran the earlier one.

create or replace function is_people_memory_owner()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select nullif(auth.jwt() ->> 'email', '') is not null
     and nullif(auth.jwt() ->> 'email', '')
         = nullif((select value from app_settings where key = 'owner_email'), '');
$$;

-- CREATE OR REPLACE keeps the existing ACL, but state it anyway so this file is correct on its own.
revoke all on function is_people_memory_owner() from public;
revoke execute on function is_people_memory_owner() from anon;
grant execute on function is_people_memory_owner() to authenticated;
