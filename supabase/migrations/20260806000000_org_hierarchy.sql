alter table orgs add column if not exists parent_org_id bigint references orgs(id) on delete set null;
create index if not exists orgs_parent_idx on orgs(parent_org_id);
