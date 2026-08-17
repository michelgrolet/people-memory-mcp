-- Identifier lookup and identifier uniqueness disagreed about case.
--
-- `_person_candidates` has always matched on `lower(i.value) = %s`, so as far as reading is
-- concerned an identifier is case-insensitive. Writing did not agree: only `email` was lowercased
-- before insert, everything else was stored as typed, and the primary key is `(kind, value)`,
-- which is case-sensitive. So `linkedin.com/in/ada` and `LinkedIn.com/in/Ada` are two rows the
-- `on conflict (kind, value)` clause cannot see as one.
--
-- The consequence is not a duplicate row, it is a person who can no longer be resolved: the next
-- lookup lowercases the query, matches both rows, finds two candidates, and returns
-- needs_confirmation forever. Nothing in the product can dig them back out.
--
-- On the installation this was found on: 178 of 2,962 `linkedin` identifiers carried uppercase and
-- had not collided yet, and one `email` address existed twice on the same person in two cases.
--
-- The fix is to make storage agree with lookup rather than the other way round, because the
-- lookup's behaviour is the one the product already promises. Note the trade this locks in: an
-- identifier kind whose value is genuinely case-sensitive can no longer be stored faithfully.
-- None of the kinds in use are (email, phone, whatsapp, linkedin, github, x, instagram, facebook,
-- website, google_rn). Adding one later means revisiting this constraint on purpose, which is the
-- point of writing it down as a constraint rather than leaving it to the Python.

-- One transaction on purpose. Step 2 below can abort deliberately, and psql runs a bare file one
-- statement at a time, so without this a stopped migration would leave the table deduplicated but
-- neither folded nor constrained.
begin;

-- 1. Two rows for the same person differing only by case are one row. Keep the primary if there is
--    one, then the lowercase one, then whichever comes first.
--    `count(distinct ...) over ()` is not implemented in Postgres, so one owner is expressed as
--    min(person_id) = max(person_id) over the same window.
with ranked as (
  select ctid,
         row_number() over (
           partition by kind, lower(value)
           order by is_primary desc, (value = lower(value)) desc, observed_at, ctid
         ) as rn,
         min(person_id) over (partition by kind, lower(value)) as first_owner,
         max(person_id) over (partition by kind, lower(value)) as last_owner
  from identifiers
)
delete from identifiers i
using ranked r
where i.ctid = r.ctid and r.rn > 1 and r.first_owner = r.last_owner;

-- 2. If a case collision spans two different people, that is a merge decision and this migration
--    must not guess. Stop, and let a human use the merge screen first.
do $$
declare clash int;
begin
  select count(*) into clash from (
    select kind, lower(value)
    from identifiers
    group by kind, lower(value)
    having count(distinct person_id) > 1
  ) s;
  if clash > 0 then
    raise exception
      'Migration stopped: % identifier value(s) differ only by case but belong to different people. Merge those people first, then re-run.', clash;
  end if;
end $$;

-- 3. Now that nothing collides, fold the remaining values down.
update identifiers set value = lower(value) where value <> lower(value);

-- 4. Make the database the guarantee instead of the caller. With every value lowercase, the
--    existing primary key on (kind, value) is a case-insensitive one.
alter table identifiers
  add constraint identifiers_value_is_lowercase check (value = lower(value));

commit;
