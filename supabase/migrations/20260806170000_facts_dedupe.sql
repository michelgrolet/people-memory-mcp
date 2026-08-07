-- Non-idempotent sync writes (each LinkedIn import/sync pass re-inserted the same fact) had
-- accumulated exact duplicates in `facts` (same person_id/key/value, different id). Clean up the
-- existing duplicates, keeping the earliest row, then add a partial unique index so future writers
-- can `ON CONFLICT (...) WHERE value IS NOT NULL DO NOTHING` and stay idempotent.
--
-- The index covers `date`/`num` too: two observations of the same key/value at two different
-- dates (e.g. a recurring numeric reading) are distinct facts, not duplicates, and must not
-- collapse into one row. Plain `(person_id, key, value, date, num)` would not actually enforce
-- that in Postgres, though: a unique index treats every NULL as distinct from every other NULL,
-- so rows that never set `date`/`num` (e.g. `linkedin_connected_on`, which encodes the date in
-- `value` and leaves `date`/`num` NULL) would stop deduping at all - reintroducing the exact bug
-- this migration exists to fix. COALESCE both columns to a sentinel ('-infinity' / NaN) so "no
-- date/num recorded" is one consistent group instead of "always distinct". Both sentinels are
-- real Postgres literals that a genuine person fact will not plausibly contain.
delete from facts a
using facts b
where a.id > b.id
  and a.person_id = b.person_id
  and a.key = b.key
  and a.value = b.value
  and a.value is not null
  and coalesce(a.date, '-infinity'::date) = coalesce(b.date, '-infinity'::date)
  and coalesce(a.num, 'NaN'::double precision) = coalesce(b.num, 'NaN'::double precision);

create unique index if not exists facts_person_key_value_date_num_uidx
  on facts (
    person_id,
    key,
    value,
    coalesce(date, '-infinity'::date),
    coalesce(num, 'NaN'::double precision)
  )
  where value is not null;
