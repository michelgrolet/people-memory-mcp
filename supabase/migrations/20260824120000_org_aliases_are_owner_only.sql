-- `org_aliases` shipped without row level security, and in this schema that is not a neutral
-- omission.
--
-- 20260803000100_security.sql ends with
-- `alter default privileges in schema public grant select, insert, update, delete on tables to
-- authenticated`. So a table created by a later migration is granted to `authenticated`
-- automatically, and gets no policy automatically. RLS off means the grant is the whole story:
-- every table added after that migration is fully readable and writable by any signed-in role
-- until someone remembers to lock it. `org_aliases` was the first one to actually take that path.
--
-- What leaks is not incidental either. An alias row is a name a human typed at the merge screen,
-- which is to say an employer of someone in the graph, next to the id of the organisation it
-- resolves to — the same class of third-party data every other table here protects.
--
-- The fix is the pattern the other nine tables already use: enable, force, one `owner_only`
-- policy. `force` matters because the table owner otherwise bypasses its own policy, and the
-- migrations run as the owner.

begin;

alter table org_aliases enable row level security;
alter table org_aliases force row level security;

drop policy if exists owner_only on org_aliases;
create policy owner_only on org_aliases
  for all to authenticated
  using (is_people_memory_owner())
  with check (is_people_memory_owner());

-- Belt and braces, same as the security migration: the default privileges revoke covers tables
-- created after it ran, but an installation that has been through several hands may have had that
-- default changed.
revoke all on org_aliases from anon;
grant select, insert, update, delete on org_aliases to authenticated;

commit;
