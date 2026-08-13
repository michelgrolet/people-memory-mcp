-- Fixing a duplicate by hand is six writes across five tables, and a browser doing them one REST
-- call at a time can stop in the middle: a person whose facts moved but whose links did not is
-- worse than the duplicate was. These four functions each do their whole job in one statement from
-- the caller's side, so a failure leaves the graph exactly as it was.
--
-- They are `security invoker` like the rest: RLS decides, and a stranger who reaches the RPC finds
-- no rows to act on. `anon` loses execute anyway — Supabase grants it by default on every new
-- function (see 20260808120000), and a merge endpoint callable without signing in is not something
-- to leave lying around even when it can do nothing.
--
-- None of them decides anything. Which record survives is an argument, chosen by the person
-- clicking; the losing record is written to `deleted_records` in full first, so the decision is
-- recoverable.

-- ── people ───────────────────────────────────────────────────────────────────

create or replace function merge_people(keep_id bigint, drop_id bigint)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
  snapshot jsonb;
  blocking text;
  n_identifiers int; n_affiliations int; n_facts int; n_interactions int; n_edges int;
begin
  if keep_id = drop_id then
    raise exception 'merge_people: keep and drop are the same record (%)', keep_id;
  end if;

  -- The full losing record, captured before anything moves. Taken through the same `deleted_records`
  -- table `delete_person` writes to, with the surviving id added so the pair can be read back.
  select jsonb_build_object(
    'person', to_jsonb(p),
    'merged_into', keep_id,
    'identifiers', coalesce((select jsonb_agg(to_jsonb(i)) from identifiers i where i.person_id = drop_id), '[]'::jsonb),
    'affiliations', coalesce((select jsonb_agg(to_jsonb(a)) from affiliations a where a.person_id = drop_id), '[]'::jsonb),
    'facts', coalesce((select jsonb_agg(to_jsonb(f)) from facts f where f.person_id = drop_id), '[]'::jsonb),
    'interactions', coalesce((select jsonb_agg(to_jsonb(x)) from interactions x where x.person_id = drop_id), '[]'::jsonb),
    'edges', coalesce((select jsonb_agg(to_jsonb(e)) from edges e where e.a_id = drop_id or e.b_id = drop_id), '[]'::jsonb)
  )
  into snapshot
  from people p
  where p.id = drop_id;

  if snapshot is null then
    raise exception 'merge_people: record % not found', drop_id;
  end if;
  if not exists (select 1 from people where id = keep_id) then
    raise exception 'merge_people: record % not found', keep_id;
  end if;

  -- A family link between the two is somebody having already decided they are different people —
  -- a son named after his father, two sisters given the same name. Refuse rather than obey: the
  -- caller has to remove the link first, which is a deliberate act and a visible one.
  select string_agg(distinct kind, ', ') into blocking
  from edges
  where kind in ('parent', 'sibling', 'partner')
    and ((a_id = keep_id and b_id = drop_id) or (a_id = drop_id and b_id = keep_id));
  if blocking is not null then
    raise exception 'merge_people: % and % are linked as % — they are two people, not one record twice',
      keep_id, drop_id, blocking;
  end if;

  insert into deleted_records (record_type, record_id, payload)
  values ('person_merged', drop_id, snapshot);

  -- Anything the survivor does not have, it inherits. A merge must never be the reason the only
  -- recorded birthday disappears.
  update people k set
    first_name    = coalesce(k.first_name, d.first_name),
    last_name     = coalesce(k.last_name, d.last_name),
    birthdate     = coalesce(k.birthdate, d.birthdate),
    birthday_md   = coalesce(k.birthday_md, d.birthday_md),
    city          = coalesce(k.city, d.city),
    country       = coalesce(k.country, d.country),
    current_org   = coalesce(k.current_org, d.current_org),
    "current_role"= coalesce(k."current_role", d."current_role"),
    linkedin_url  = coalesce(k.linkedin_url, d.linkedin_url),
    met_where     = coalesce(k.met_where, d.met_where),
    met_when      = coalesce(k.met_when, d.met_when),
    -- tie strength is a judgement someone made; the closer of the two is the one that was observed
    tie_strength  = nullif(greatest(coalesce(k.tie_strength, 0), coalesce(d.tie_strength, 0)), 0),
    -- a summary is prose somebody wrote. Two of them are appended, never silently reduced to one.
    summary       = case
                      when coalesce(trim(d.summary), '') = '' then k.summary
                      when coalesce(trim(k.summary), '') = '' then d.summary
                      when trim(k.summary) = trim(d.summary) then k.summary
                      else k.summary || E'\n\n' || d.summary
                    end
  from people d
  where k.id = keep_id and d.id = drop_id;

  -- `identifiers` is keyed on (kind, value) across the whole table, so an address can only ever sit
  -- on one record and moving it can never collide.
  update identifiers set person_id = keep_id where person_id = drop_id;
  get diagnostics n_identifiers = row_count;

  update interactions set person_id = keep_id where person_id = drop_id;
  get diagnostics n_interactions = row_count;

  -- The three below can collide with something the survivor already holds — the same job, the same
  -- fact, the same link. `on conflict do nothing` keeps the survivor's row; the loser's copy is in
  -- the snapshot either way.
  insert into affiliations (person_id, org_id, role, since, until, source, observed_at)
  select keep_id, a.org_id, a.role, a.since, a.until, a.source, a.observed_at
  from affiliations a where a.person_id = drop_id
  on conflict do nothing;
  get diagnostics n_affiliations = row_count;

  insert into facts (person_id, key, value, num, date, source, observed_at, confidence, created_at)
  select keep_id, f.key, f.value, f.num, f.date, f.source, f.observed_at, f.confidence, f.created_at
  from facts f where f.person_id = drop_id
  on conflict do nothing;
  get diagnostics n_facts = row_count;

  -- An edge whose other end is the survivor would become a link to itself, which the table refuses;
  -- it is dropped rather than rewritten. The canonicalizing trigger fires on these inserts and may
  -- swap the ends, so the conflict check below sees the final orientation, not this one.
  insert into edges (a_id, b_id, kind, strength, since, until, note, source, observed_at)
  select case when e.a_id = drop_id then keep_id else e.a_id end,
         case when e.b_id = drop_id then keep_id else e.b_id end,
         e.kind, e.strength, e.since, e.until, e.note, e.source, e.observed_at
  from edges e
  where (e.a_id = drop_id or e.b_id = drop_id)
    and (case when e.a_id = drop_id then keep_id else e.a_id end)
     <> (case when e.b_id = drop_id then keep_id else e.b_id end)
  on conflict do nothing;
  get diagnostics n_edges = row_count;

  -- Whatever is left on the loser is carried away by the `on delete cascade` on every child table.
  delete from people where id = drop_id;

  return jsonb_build_object(
    'kept', keep_id, 'dropped', drop_id,
    'identifiers', n_identifiers, 'affiliations', n_affiliations,
    'facts', n_facts, 'interactions', n_interactions, 'edges', n_edges
  );
end;
$$;

-- ── organizations ────────────────────────────────────────────────────────────

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

  delete from orgs where id = drop_id;

  return jsonb_build_object(
    'kept', keep_id, 'dropped', drop_id,
    'affiliations', n_affiliations, 'children', n_children, 'current_org', n_current_org
  );
end;
$$;

create or replace function delete_org(p_id bigint)
returns boolean
language plpgsql
security invoker
set search_path = public
as $$
declare
  snapshot jsonb;
begin
  select jsonb_build_object(
    'org', to_jsonb(o),
    'affiliations', coalesce((select jsonb_agg(to_jsonb(a)) from affiliations a where a.org_id = p_id), '[]'::jsonb),
    'children', coalesce((select jsonb_agg(to_jsonb(c)) from orgs c where c.parent_org_id = p_id), '[]'::jsonb)
  )
  into snapshot
  from orgs o
  where o.id = p_id;

  if snapshot is null then
    return false;
  end if;

  insert into deleted_records (record_type, record_id, payload)
  values ('org', p_id, snapshot);
  -- affiliations cascade; a subsidiary keeps existing and loses its parent, per the column's own rule
  delete from orgs where id = p_id;
  return true;
end;
$$;

-- ── links ────────────────────────────────────────────────────────────────────

-- Retyping a link means changing part of its primary key, and for `parent` it can also mean
-- swapping its ends. Both at once is a delete and an insert, which is exactly the pair that must
-- not half-happen: a family link that vanished without its replacement is worse than a vague one.
create or replace function set_edge_kind(
  p_a_id bigint, p_b_id bigint, p_old_kind text, p_new_kind text, p_swap boolean default false
)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
  src edges%rowtype;
  new_a bigint;
  new_b bigint;
begin
  if p_a_id = p_b_id then
    raise exception 'set_edge_kind: a link needs two different people';
  end if;

  -- The old link is looked up in both orientations: symmetric kinds are stored canonically, so the
  -- caller cannot know which way round the stored row runs.
  select * into src from edges
  where kind = p_old_kind
    and ((a_id = p_a_id and b_id = p_b_id) or (a_id = p_b_id and b_id = p_a_id));
  if not found then
    raise exception 'set_edge_kind: no % link between % and %', p_old_kind, p_a_id, p_b_id;
  end if;

  if p_swap then new_a := p_b_id; new_b := p_a_id;
  else            new_a := p_a_id; new_b := p_b_id;
  end if;

  delete from edges where kind = src.kind and a_id = src.a_id and b_id = src.b_id;

  -- Everything the link already carried is kept: its note is usually the only record of why it was
  -- drawn, and the whole point of retyping is that the note was right and the kind was not.
  insert into edges (a_id, b_id, kind, strength, since, until, note, source, observed_at)
  values (new_a, new_b, p_new_kind, src.strength, src.since, src.until, src.note, src.source, src.observed_at)
  on conflict (a_id, b_id, kind) do update
    set note = coalesce(edges.note, excluded.note),
        since = coalesce(edges.since, excluded.since),
        until = coalesce(edges.until, excluded.until);

  return jsonb_build_object('a_id', new_a, 'b_id', new_b, 'kind', p_new_kind);
end;
$$;

-- Both revokes are needed, and for different reasons. Postgres grants execute to PUBLIC on every new
-- function; Supabase adds a *direct* grant to `anon` on top of it (see 20260808120000). Dropping
-- either one alone leaves the other standing, and the function stays callable at
-- `/rest/v1/rpc/<name>` without signing in.
revoke execute on function merge_people(bigint, bigint) from public, anon;
revoke execute on function merge_orgs(bigint, bigint) from public, anon;
revoke execute on function delete_org(bigint) from public, anon;
revoke execute on function set_edge_kind(bigint, bigint, text, text, boolean) from public, anon;
grant execute on function merge_people(bigint, bigint) to authenticated;
grant execute on function merge_orgs(bigint, bigint) to authenticated;
grant execute on function delete_org(bigint) to authenticated;
grant execute on function set_edge_kind(bigint, bigint, text, text, boolean) to authenticated;
