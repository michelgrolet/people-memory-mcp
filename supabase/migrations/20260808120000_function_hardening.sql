-- Two findings from Supabase's database linter on a real installation, both in code this repo ships.
--
-- 1. `revoke all on function is_people_memory_owner() from public` is not enough on Supabase.
--    Supabase ships `alter default privileges ... grant execute on functions to anon, authenticated`,
--    so a new function gets a *direct* grant to `anon` on top of the PUBLIC one. Revoking from PUBLIC
--    leaves the direct grant untouched: measured on a live project, the ACL reads
--    `postgres=X/postgres | anon=X/postgres | ...` — PUBLIC gone, `anon` still there. So
--    `/rest/v1/rpc/is_people_memory_owner` stays callable without signing in. It only ever returns
--    false to a stranger, but a `security definer` function reachable by `anon` is not something to
--    leave lying around, and the linter is right to flag it.
--
-- 2. The four functions in `core.sql` had no `set search_path`. They are `security invoker`, so this
--    is not a privilege escalation path, but a mutable `search_path` still means the function body
--    resolves names against whatever the caller has set. Pinning it is free.
--
-- Both are also fixed at the source, so a fresh install never has the problem. This migration exists
-- for the installations that already ran the earlier ones.

revoke execute on function is_people_memory_owner() from anon;

alter function canonicalize_symmetric_edge() set search_path = public;
alter function touch_updated_at() set search_path = public;
alter function delete_person(bigint) set search_path = public;
alter function find_intro_paths(text, text, integer) set search_path = public;
