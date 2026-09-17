-- Some people you want to actually talk to on a schedule: parents every two weeks, a close friend
-- once a month. A to-do app holds that badly, because the reminder knows nothing about the call
-- that happened yesterday. The graph does know: every call, meal and meeting is an interaction row.
-- So the cadence lives on the person, the last real conversation is read off the interactions, and
-- who is due comes out of a view instead of a list somebody has to keep by hand.
--
-- A "call" here is any live conversation: voice, video, or in person. A WhatsApp or an email keeps
-- `last_contact` fresh but does not reset the clock, because that is the whole point of the clock.

begin;

alter table people
  add column if not exists call_every_days integer
  check (call_every_days is null or call_every_days > 0);

comment on column people.call_every_days is
  'How often you want a live conversation with this person, in days. Null means no schedule.';

-- One place that says which channels count as a live conversation, shared by the view and by
-- anything that wants to ask the question itself.
create or replace function is_live_channel(channel text)
returns boolean
language sql
immutable
as $$
  select channel is not null
     and channel ~* '(call|phone|meet|video|visio|facetime|in.?person|irl|drinks|coffee|lunch|dinner|breakfast|meeting|calendar)'
     and channel !~* 'booked';
$$;

-- Left executable by every role on purpose. `person` runs as whoever reads it (security_invoker),
-- so any role that can read the graph, the dashboard's signed-in user or a database role an agent
-- connects with, needs to call this. It is a regex over a string and reads no table, so there is
-- nothing to protect.
grant execute on function is_live_channel(text) to public;

-- `person` is `select p.*` frozen at the moment the view was created, and `create or replace view`
-- only appends columns. Rebuilding it means dropping it, and everything on top of it goes with it,
-- so those views are saved first and put back verbatim afterwards, the way 20260809000000 did.
do $$
declare
  saved record;
  progressed boolean;
begin
  create temp table cc_saved_views on commit drop as
  with recursive dependents as (
    select c.oid
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relname = 'person' and c.relkind = 'v'
    union
    select distinct rv.ev_class
    from pg_depend d
    join pg_rewrite rv on rv.oid = d.objid
    join dependents dep on dep.oid = d.refobjid
    where d.classid = 'pg_rewrite'::regclass
      and d.refclassid = 'pg_class'::regclass
      and rv.ev_class <> dep.oid
  )
  select c.relname::text as name,
         pg_get_viewdef(c.oid, true) as definition,
         c.reloptions as options,
         false as restored
  from dependents dep
  join pg_class c on c.oid = dep.oid
  where c.relname <> 'person';

  create temp table cc_saved_grants on commit drop as
  select grantee::text, privilege_type::text, table_name::text
  from information_schema.role_table_grants
  where table_schema = 'public'
    and table_name in (select name from cc_saved_views)
    and grantee <> current_user;

  drop view if exists person cascade;

  create view person
  with (security_invoker = true)
  as
  select p.*,
         case
           when p.birthdate is not null then
             extract(year from age(current_date, p.birthdate))::int
         end as age,
         lc.last_contact,
         current_date - coalesce(lc.last_contact, p.created_at::date) as days_since_contact,
         lc.last_call,
         current_date - lc.last_call as days_since_call,
         case
           when p.call_every_days is not null then
             coalesce(lc.last_call, p.created_at::date) + p.call_every_days
         end as call_due_on
  from people p
  left join lateral (
    select max(i.happened_on) as last_contact,
           max(i.happened_on) filter (where is_live_channel(i.channel)) as last_call
    from interactions i
    where i.person_id = p.id
  ) lc on true;

  loop
    progressed := false;
    for saved in select * from cc_saved_views where not restored loop
      begin
        execute format(
          'create view %I %s as %s',
          saved.name,
          case
            when saved.options is null then ''
            else format('with (%s)', array_to_string(saved.options, ', '))
          end,
          saved.definition
        );
        update cc_saved_views set restored = true where name = saved.name;
        progressed := true;
      exception
        when others then null;
      end;
    end loop;
    exit when not progressed;
  end loop;

  for saved in select name from cc_saved_views where not restored loop
    raise exception 'could not restore view %', saved.name;
  end loop;

  for saved in select * from cc_saved_grants loop
    execute format(
      'grant %s on %I to %I', saved.privilege_type, saved.table_name, saved.grantee
    );
  end loop;
end $$;

-- Who to call, most overdue first. `overdue_days` is negative while the call is still ahead.
drop view if exists calls_due;
create view calls_due
with (security_invoker = true)
as
select full_name as name,
       current_org as org,
       call_every_days,
       last_call,
       days_since_call,
       call_due_on,
       current_date - call_due_on as overdue_days,
       id
from person
where call_every_days is not null
order by call_due_on, full_name;

-- Same grants as every other view here: the tables under them carry the row level security, and
-- `security_invoker` makes the view run as the caller.
grant select on person, calls_due to authenticated;
revoke all on person, calls_due from anon;

commit;
