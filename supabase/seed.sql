insert into people (full_name, current_org, "current_role", city, tie_strength, summary)
values
  ('Ada Lovelace', 'Analytical Engine', 'Mathematician', 'London', 4, 'Demo record'),
  ('Grace Hopper', 'US Navy', 'Computer scientist', 'Arlington', 3, 'Demo record'),
  ('Alan Turing', 'Bletchley Park', 'Mathematician', 'Manchester', 3, 'Demo record')
on conflict do nothing;

insert into edges (a_id, b_id, kind, strength, source)
select a.id, b.id, 'knows', 3, 'demo'
from people a, people b
where a.full_name = 'Ada Lovelace' and b.full_name = 'Grace Hopper'
on conflict do nothing;
