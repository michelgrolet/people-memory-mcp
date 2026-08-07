alter table people add column if not exists kind text not null default 'human';
create index if not exists people_kind_idx on people(kind);
