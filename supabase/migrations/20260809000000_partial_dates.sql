-- `facts.date`, `affiliations.since`/`until` and `edges.since`/`until` become partial dates: ISO-8601
-- prefixes in text (`YYYY`, `YYYY-MM`, `YYYY-MM-DD`) instead of `date` columns.
--
-- Why: real facts about people carry incomplete dates. Someone joined a company "in 2015", a
-- relationship ended "in 2023-09". A `date` column can only hold that by inventing a month and a day,
-- and inventing data to satisfy a column type is worse than admitting the day is unknown. Same
-- reasoning that already put `birthday_md` next to `birthdate` for year-less birthdays. Measured on a
-- real installation before making the change: of 59 filled values across these five columns, 55 were
-- partial, and every filled `affiliations.until` was. The full rationale, including why the check is
-- repeated per column instead of living in a domain, is at the top of the core migration.
--
-- Two starting states, both handled. A base created by these migrations has the columns as `date` and
-- needs a real conversion. A base that predates them (`create table if not exists` is a no-op on a
-- table that already exists, so the declared type never applied) already has text and needs only the
-- constraint. The type-changing path is the risky one, so it runs only when there is a type to
-- change.

-- Nothing that cannot be converted, checked before a single byte moves, and reported all at once so
-- one run tells the operator everything to fix. `2019-2020` is a range and `ongoing` is a status:
-- both are real information, both belong in a text field next to the fact, and choosing where is the
-- operator's call rather than a migration's.
do $$
declare
  offenders text;
begin
  select string_agg(format('%s.%s = %L', src, col, val), ', ' order by src, col, val)
    into offenders
  from (
    select 'facts' as src, 'date' as col, f.date::text as val from facts f where f.date is not null
    union all
    select 'affiliations', 'since', a.since::text from affiliations a where a.since is not null
    union all
    select 'affiliations', 'until', a.until::text from affiliations a where a.until is not null
    union all
    select 'edges', 'since', e.since::text from edges e where e.since is not null
    union all
    select 'edges', 'until', e.until::text from edges e where e.until is not null
  ) candidates
  where val !~ '^\d{4}(-\d{2}(-\d{2})?)?$';

  if offenders is not null then
    raise exception 'These values are not dates and would be lost: %', offenders
      using hint = 'Move each one into a text field, then run this migration again.';
  end if;
end
$$;

-- Dropped before the conversion, not after: this index keys on `coalesce(date, '-infinity'::date)`,
-- and `alter column type` re-resolves every dependent expression, so leaving it in place fails the
-- conversion with "COALESCE types text and date cannot be matched". It is rebuilt at the bottom of
-- this file with a sentinel that works on text.
drop index if exists facts_person_key_value_date_num_uidx;

-- The conversion, for installations where these columns really are `date`.
--
-- Postgres refuses `alter column type` while a view reads the column, and dropping a view discards
-- its grants along with it, so both are captured and put back. `pg_get_viewdef` is used rather than
-- repeating the view bodies here, which keeps this migration correct when the views change later and
-- preserves any view the operator added on top of them. Recreation is attempted in rounds instead of
-- a computed dependency order: a view that fails because its dependency is not back yet simply
-- succeeds on a later round, and the loop stops when a round adds nothing.
do $$
declare
  target record;
  saved record;
  progressed boolean;
  still_missing text;
begin
  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'public'
      and (table_name, column_name) in
          (('facts', 'date'), ('affiliations', 'since'), ('affiliations', 'until'),
           ('edges', 'since'), ('edges', 'until'))
      and data_type = 'date'
  ) then
    return;
  end if;

  create temp table pd_saved_views on commit drop as
  with recursive dependents as (
    select view_class.oid
    from pg_depend d
    join pg_rewrite r on r.oid = d.objid
    join pg_class view_class on view_class.oid = r.ev_class
    join pg_class src on src.oid = d.refobjid
    join pg_attribute att on att.attrelid = d.refobjid and att.attnum = d.refobjsubid
    where src.relnamespace = 'public'::regnamespace
      and src.relname in ('facts', 'affiliations', 'edges')
      and att.attname in ('date', 'since', 'until')
      and view_class.relkind = 'v'
    union
    select view_class.oid
    from dependents dep
    join pg_depend d on d.refobjid = dep.oid
    join pg_rewrite r on r.oid = d.objid
    join pg_class view_class on view_class.oid = r.ev_class
    where view_class.relkind = 'v' and view_class.oid <> dep.oid
  )
  select c.relname::text as name,
         pg_get_viewdef(c.oid, true) as definition,
         c.reloptions as options,
         false as restored
  from dependents dep
  join pg_class c on c.oid = dep.oid;

  create temp table pd_saved_grants on commit drop as
  select grantee::text, privilege_type::text, table_name::text
  from information_schema.role_table_grants
  where table_schema = 'public'
    and table_name in (select name from pd_saved_views)
    and grantee <> current_user;

  for saved in select name from pd_saved_views loop
    execute format('drop view if exists %I cascade', saved.name);
  end loop;

  -- One statement per table, covering every column of it at once. Converting `since` and `until`
  -- in two statements fails: after the first, the table's own `until >= since` check compares a
  -- date to text and Postgres has no such operator. A single ALTER TABLE re-checks constraints once,
  -- at the end, when both sides are text again.
  --
  -- to_char, not a plain cast: `date::text` follows the session's DateStyle, so a server set to
  -- German or SQL style would write 01.04.2022 into a column whose constraint demands ISO.
  for target in
    select v.tbl,
           string_agg(
             format('alter column %I type text using to_char(%I, %L)', v.col, v.col, 'YYYY-MM-DD'),
             ', ' order by v.col
           ) as clauses
    from (values ('facts', 'date'), ('affiliations', 'since'), ('affiliations', 'until'),
                 ('edges', 'since'), ('edges', 'until')) as v(tbl, col)
    join information_schema.columns c
      on c.table_schema = 'public'
     and c.table_name = v.tbl
     and c.column_name = v.col
     and c.data_type = 'date'
    group by v.tbl
  loop
    execute format('alter table %I %s', target.tbl, target.clauses);
  end loop;

  loop
    progressed := false;
    for saved in select * from pd_saved_views where not restored loop
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
        update pd_saved_views set restored = true where name = saved.name;
        progressed := true;
      exception
        when others then null;
      end;
    end loop;
    exit when not progressed;
  end loop;

  select string_agg(name, ', ' order by name) into still_missing
  from pd_saved_views where not restored;
  if still_missing is not null then
    raise exception 'Could not rebuild these views after the conversion: %', still_missing;
  end if;

  for saved in select * from pd_saved_grants loop
    execute format(
      'grant %s on %I to %I', saved.privilege_type, saved.table_name, saved.grantee
    );
  end loop;
end
$$;

-- The constraint itself, on both paths. Named so a second run is a no-op rather than a duplicate.
do $$
declare
  target record;
  constraint_name text;
begin
  for target in
    select * from (values ('facts', 'date'), ('affiliations', 'since'), ('affiliations', 'until'),
                          ('edges', 'since'), ('edges', 'until')) as v(tbl, col)
  loop
    constraint_name := format('%s_%s_partial_date_check', target.tbl, target.col);
    if not exists (
      select 1 from pg_constraint
      where conname = constraint_name and conrelid = format('public.%I', target.tbl)::regclass
    ) then
      execute format(
        'alter table %I add constraint %I check (%I is null or %I ~ %L)',
        target.tbl, constraint_name, target.col, target.col,
        '^\d{4}(-\d{2}(-\d{2})?)?$'
      );
    end if;
  end loop;
end
$$;

-- Rebuilt with the empty string as the "no date recorded" sentinel, which the constraint above
-- rejects, so it cannot collide with a real value. repository.py's add_fact keys its ON CONFLICT on
-- exactly this expression, and a mismatch there means every fact insert raises instead of deduping.
create unique index if not exists facts_person_key_value_date_num_uidx
  on facts (
    person_id,
    key,
    value,
    coalesce(date, ''),
    coalesce(num, 'NaN'::double precision)
  )
  where value is not null;
