-- Organisations were deduplicated by hand, and the next import undid it.
--
-- `orgs.name` is unique on the exact string, so "Armée de terre" and "Armée de Terre" are two
-- rows. Every importer writes the casing it was handed — LinkedIn returns whatever each member
-- typed into their own profile — so `insert into orgs (name) ... on conflict (name)` creates a
-- second organisation instead of finding the first. On this installation, four organisations
-- merged by hand on 13/08 were recreated by the weekly LinkedIn sync a few hours later, and they
-- were the only four organisations created that day. A weekly cleanup cannot win against a weekly
-- import: the fix has to be at the moment of writing.
--
-- Two mechanisms, because there are two different kinds of duplicate:
--
-- 1. Same name, written differently. Case, accents, punctuation, spacing, a trailing legal suffix
--    ("ITrust" / "ITrust SA"). This is decidable without judgement, so `org_norm()` decides it.
--    The rule is deliberately narrow. Similarity would be the tempting tool and it is the wrong
--    one: on this installation 73 pairs of organisations score above 0.4 trigram similarity and
--    nearly all of them are genuinely different companies — BNP Paribas / BNP Paribas CIB,
--    KNDS France / KPMG France, CS GROUP / NAVAL GROUP. Merging two real companies is much worse
--    than keeping a duplicate, so nothing here merges on resemblance. Note what is *not* stripped:
--    "Groupe"/"Group", because "Groupe TF1" and "TF1" may or may not be the same legal entity and
--    this function is not entitled to that opinion.
--
-- 2. Different name, same organisation. "2600" and "Ecole 2600". No deterministic rule finds that
--    and no rule should: it is a human judgement. But it is a judgement someone already made, once,
--    at the merge screen — and then threw away. `org_aliases` keeps it, so a merge decided once is
--    applied to every future import. That is what turns cleanup into progress instead of chores.
--
-- The canonicalisation is a BEFORE INSERT trigger rather than only application code, because the
-- database has more than one writer: the MCP server, the CLI importers, and the web client through
-- PostgREST. A rule that lives in one caller is a rule the other callers break. The trigger rewrites
-- the incoming name to the surviving one, which means an `on conflict (name) do update ... returning
-- id` insert — what every importer already does — returns the existing organisation's id and writes
-- nothing new. It is also why an installation gets the fix the moment this migration is applied,
-- without waiting for its checkout to be updated: the guarantee sits under the caller, not in it.
--
-- Escape hatch, on purpose: only INSERT is canonicalised, never UPDATE. If two organisations really
-- do normalise to the same key and both must exist, insert and then rename.

begin;

-- `strict` so a null name returns null instead of the empty string, `immutable` so the expression
-- can be indexed. `lower()` runs before `translate()`, so only lowercase accented characters need
-- to be listed.
create or replace function org_norm(value text)
returns text
language plpgsql
immutable
strict
set search_path = public
as $$
declare
  -- Suffixes are stripped only from the END of the name, and never the last remaining token, so
  -- an organisation actually called "SA" survives.
  suffixes text[] := array[
    'sa', 'sas', 'sasu', 'sarl', 'eurl', 'sci', 'snc', 'cie',
    'inc', 'llc', 'ltd', 'limited', 'plc', 'corp', 'corporation', 'company', 'co',
    'gmbh', 'ag', 'bv', 'nv', 'ab', 'oy', 'aps', 'spa', 'srl', 'pty', 'kk'
  ];
  tokens text[];
  index int;
begin
  tokens := array_remove(
    regexp_split_to_array(
      btrim(
        regexp_replace(
          translate(
            lower(value),
            'àáâãäåçèéêëìíîïñòóôõöùúûüýÿœæ',
            'aaaaaaceeeeiiiinooooouuuuyyoa'
          ),
          '[^a-z0-9]+', ' ', 'g'
        )
      ),
      ' '
    ),
    ''
  );

  while coalesce(array_length(tokens, 1), 0) > 1
        and tokens[array_length(tokens, 1)] = any (suffixes) loop
    tokens := tokens[1 : array_length(tokens, 1) - 1];
  end loop;

  -- The one synonym worth hard-coding: LinkedIn profiles carry both spellings of the same
  -- non-employer, and they had already produced a duplicate pair here.
  for index in 1 .. coalesce(array_length(tokens, 1), 0) loop
    if tokens[index] in ('freelancer', 'freelancing') then
      tokens[index] := 'freelance';
    end if;
  end loop;

  return coalesce(array_to_string(tokens, ' '), '');
end;
$$;

-- A name that a human decided points at an existing organisation. `alias` is already normalised.
create table if not exists org_aliases (
  alias text primary key check (length(trim(alias)) > 0),
  org_id bigint not null references orgs(id) on delete cascade,
  source text not null default 'merge',
  created_at timestamptz not null default now()
);

create index if not exists org_aliases_org_idx on org_aliases (org_id);

-- What the trigger and the importer both look up.
create index if not exists orgs_norm_name_idx on orgs (org_norm(name));

create or replace function orgs_canonicalize_name()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
declare
  canonical text;
  key text := org_norm(new.name);
begin
  if coalesce(key, '') = '' then
    return new;
  end if;

  select o.name into canonical
  from orgs o
  where org_norm(o.name) = key
  order by o.id
  limit 1;

  if canonical is null then
    select o.name into canonical
    from org_aliases a
    join orgs o on o.id = a.org_id
    where a.alias = key
    limit 1;
  end if;

  if canonical is not null then
    new.name := canonical;
  end if;
  return new;
end;
$$;

drop trigger if exists orgs_canonicalize_name_before_insert on orgs;
create trigger orgs_canonicalize_name_before_insert
  before insert on orgs
  for each row
  execute function orgs_canonicalize_name();

-- `merge_orgs` gains one job: remember the decision. Two statements, added to the body from
-- 20260813120000 — the dropped name becomes an alias of the survivor, and any alias the dropped
-- organisation had collected is repointed instead of being cascaded away with it.
create or replace function merge_orgs(keep_id bigint, drop_id bigint)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
  snapshot jsonb;
  keep_name text;
  drop_name text;
  n_affiliations int; n_children int; n_current_org int;
begin
  if keep_id = drop_id then
    raise exception 'merge_orgs: keep and drop are the same organization (%)', keep_id;
  end if;

  select name into keep_name from orgs where id = keep_id;
  if keep_name is null then
    raise exception 'merge_orgs: organization % not found', keep_id;
  end if;

  select jsonb_build_object(
    'org', to_jsonb(o),
    'merged_into', keep_id,
    'affiliations', coalesce((select jsonb_agg(to_jsonb(a)) from affiliations a where a.org_id = drop_id), '[]'::jsonb),
    'children', coalesce((select jsonb_agg(to_jsonb(c)) from orgs c where c.parent_org_id = drop_id), '[]'::jsonb)
  ), o.name
  into snapshot, drop_name
  from orgs o
  where o.id = drop_id;

  if snapshot is null then
    raise exception 'merge_orgs: organization % not found', drop_id;
  end if;

  insert into deleted_records (record_type, record_id, payload)
  values ('org_merged', drop_id, snapshot);

  update orgs k set
    kind    = coalesce(k.kind, d.kind),
    domain  = coalesce(k.domain, d.domain),
    city    = coalesce(k.city, d.city),
    country = coalesce(k.country, d.country),
    note    = case
                when coalesce(trim(d.note), '') = '' then k.note
                when coalesce(trim(k.note), '') = '' then d.note
                when trim(k.note) = trim(d.note) then k.note
                else k.note || E'\n\n' || d.note
              end
  from orgs d
  where k.id = keep_id and d.id = drop_id;

  insert into affiliations (person_id, org_id, role, since, until, source, observed_at)
  select a.person_id, keep_id, a.role, a.since, a.until, a.source, a.observed_at
  from affiliations a where a.org_id = drop_id
  on conflict do nothing;
  get diagnostics n_affiliations = row_count;

  -- A subsidiary of the losing name becomes a subsidiary of the surviving one, unless that would
  -- make the survivor its own parent.
  update orgs set parent_org_id = keep_id
  where parent_org_id = drop_id and id <> keep_id;
  get diagnostics n_children = row_count;
  update orgs set parent_org_id = null where id = keep_id and parent_org_id = drop_id;

  -- `people.current_org` is free text, not a foreign key: it is what the graph and the filter list
  -- read, so a merge that leaves the old name there leaves the duplicate visible everywhere it
  -- actually shows.
  update people set current_org = keep_name where current_org = drop_name;
  get diagnostics n_current_org = row_count;

  -- New: aliases the dropped organisation had collected belong to the survivor now, and would
  -- otherwise be deleted by the cascade below.
  update org_aliases set org_id = keep_id where org_id = drop_id;

  -- New: the decision itself. Without this line the next import recreates exactly what this call
  -- just merged, which is the bug this migration exists for. Skipped when the two names already
  -- normalise the same, since `org_norm` alone then covers it.
  if coalesce(org_norm(drop_name), '') <> '' and org_norm(drop_name) <> org_norm(keep_name) then
    insert into org_aliases (alias, org_id, source)
    values (org_norm(drop_name), keep_id, 'merge')
    on conflict (alias) do update set org_id = excluded.org_id, created_at = now();
  end if;

  delete from orgs where id = drop_id;

  return jsonb_build_object(
    'kept', keep_id, 'dropped', drop_id,
    'affiliations', n_affiliations, 'children', n_children, 'current_org', n_current_org
  );
end;
$$;

-- Merges that happened before this migration existed are still recorded, in the snapshot
-- `merge_orgs` writes to `deleted_records`. Recover those decisions rather than losing them.
insert into org_aliases (alias, org_id, source)
select distinct on (org_norm(d.payload->'org'->>'name'))
       org_norm(d.payload->'org'->>'name'),
       (d.payload->>'merged_into')::bigint,
       'merge_backfill'
from deleted_records d
join orgs o on o.id = (d.payload->>'merged_into')::bigint
where d.record_type = 'org_merged'
  and coalesce(org_norm(d.payload->'org'->>'name'), '') <> ''
  and org_norm(d.payload->'org'->>'name') <> org_norm(o.name)
order by org_norm(d.payload->'org'->>'name'), d.id desc
on conflict (alias) do nothing;

commit;
