create or replace function is_people_memory_owner()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  -- Fails closed on purpose. Coalescing both sides to '' made this true when both were absent
  -- (no owner row, and a token with no email claim, which is what signInAnonymously issues).
  select nullif(auth.jwt() ->> 'email', '') is not null
     and nullif(auth.jwt() ->> 'email', '')
         = nullif((select value from app_settings where key = 'owner_email'), '');
$$;

revoke all on function is_people_memory_owner() from public;
-- Supabase's default privileges grant execute on new functions to `anon` DIRECTLY, so the
-- revoke above (which only drops the PUBLIC grant) leaves it callable without signing in.
revoke execute on function is_people_memory_owner() from anon;
grant execute on function is_people_memory_owner() to authenticated;

alter table app_settings enable row level security;
alter table people enable row level security;
alter table identifiers enable row level security;
alter table orgs enable row level security;
alter table affiliations enable row level security;
alter table edges enable row level security;
alter table facts enable row level security;
alter table interactions enable row level security;
alter table deleted_records enable row level security;

alter table app_settings force row level security;
alter table people force row level security;
alter table identifiers force row level security;
alter table orgs force row level security;
alter table affiliations force row level security;
alter table edges force row level security;
alter table facts force row level security;
alter table interactions force row level security;
alter table deleted_records force row level security;

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'app_settings', 'people', 'identifiers', 'orgs', 'affiliations',
    'edges', 'facts', 'interactions', 'deleted_records'
  ] loop
    execute format('drop policy if exists owner_only on %I', table_name);
    execute format(
      'create policy owner_only on %I for all to authenticated using (is_people_memory_owner()) with check (is_people_memory_owner())',
      table_name
    );
  end loop;
end;
$$;

revoke all on all tables in schema public from anon;
revoke all on all sequences in schema public from anon;

grant usage on schema public to authenticated;
grant select, insert, update, delete on all tables in schema public to authenticated;
grant usage, select on all sequences in schema public to authenticated;
grant execute on function delete_person(bigint) to authenticated;
grant execute on function find_intro_paths(text, text, integer) to authenticated;

alter default privileges in schema public revoke all on tables from anon;
alter default privileges in schema public grant select, insert, update, delete on tables to authenticated;
alter default privileges in schema public grant usage, select on sequences to authenticated;
