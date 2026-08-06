-- Non-idempotent sync writes (each LinkedIn import/sync pass re-inserted the same fact) had
-- accumulated exact duplicates in `facts` (same person_id/key/value, different id). Clean up the
-- existing duplicates, keeping the earliest row, then add a partial unique index so future writers
-- can `ON CONFLICT (person_id, key, value) WHERE value IS NOT NULL DO NOTHING` and stay idempotent.
-- Facts with a NULL value (num-only or date-only facts) are untouched: this index does not cover
-- them, so a fact's value can still change over time and keep its history as a new row.

delete from facts a
using facts b
where a.id > b.id
  and a.person_id = b.person_id
  and a.key = b.key
  and a.value = b.value
  and a.value is not null;

create unique index if not exists facts_person_key_value_uidx
  on facts (person_id, key, value)
  where value is not null;
