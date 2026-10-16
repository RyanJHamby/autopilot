-- Autopilot control plane, core schema. Multi-tenant from day one; single owner in practice.
-- Deliberately absent: any column that could LOOSEN a guardrail (auto_merge_classes, protected paths, comms).
-- Those live in git under CODEOWNERS; the UI can only open a PR for them. The DB is never a path to weaken safety.

create table orgs (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  owner_id uuid not null,
  created_at timestamptz not null default now()
);

create table members (
  org_id uuid not null references orgs(id) on delete cascade,
  user_id uuid not null,
  role text not null check (role in ('owner', 'maintainer', 'contributor', 'viewer')),
  primary key (org_id, user_id)
);

create table projects (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references orgs(id) on delete cascade,
  repo text not null,                              -- owner/name on GitHub
  tier text not null default 'C' check (tier in ('A', 'B', 'C')),
  enabled boolean not null default false,
  priority int not null default 2 check (priority between 0 and 10),
  budget_share int not null default 0 check (budget_share between 0 and 100),
  greediness int not null default 0 check (greediness between 0 and 3),
  max_open_prs int not null default 3 check (max_open_prs between 0 and 10),
  hold_until timestamptz,
  billing text not null default 'subscription' check (billing in ('subscription', 'byok')),
  unique (org_id, repo)
);

create table grants (
  project_id uuid not null references projects(id) on delete cascade,
  user_id uuid not null,
  action text not null check (action in ('view', 'label', 'approve_tier1', 'change_levers', 'change_guardrails', 'manage_access')),
  primary key (project_id, user_id, action)
);

create table runs (                                -- the ledger: what each run cost and what came of it
  id bigint generated always as identity primary key,
  project_id uuid not null references projects(id) on delete cascade,
  issue int,
  runner text not null,
  model text not null,
  run_points int not null check (run_points >= 0),
  outcome text not null check (outcome in ('success', 'failure', 'skipped', 'cancelled')),
  pr_number int,
  tier int check (tier between 0 and 2),
  merged boolean not null default false,
  reverted boolean not null default false,
  started_at timestamptz not null default now()
);

create table audit (                               -- append-only
  id bigint generated always as identity primary key,
  org_id uuid not null references orgs(id) on delete cascade,
  actor uuid not null,
  action text not null,
  detail jsonb not null default '{}',
  at timestamptz not null default now()
);

-- ---------- access helpers (security definer so policies do not recurse) ----------
create function is_owner(o uuid) returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from members where org_id = o and user_id = auth.uid() and role = 'owner');
$$;

create function can(p uuid, a text) returns boolean language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from projects pr join members m on m.org_id = pr.org_id and m.user_id = auth.uid()
    where pr.id = p and (m.role = 'owner' or exists (
      select 1 from grants g where g.project_id = p and g.user_id = auth.uid() and g.action = a)));
$$;

-- ---------- RLS ----------
alter table orgs enable row level security;
alter table members enable row level security;
alter table projects enable row level security;
alter table grants enable row level security;
alter table runs enable row level security;
alter table audit enable row level security;

create policy orgs_read on orgs for select using (exists (select 1 from members m where m.org_id = id and m.user_id = auth.uid()));
create policy members_read on members for select using (user_id = auth.uid() or is_owner(org_id));
create policy members_write on members for all using (is_owner(org_id)) with check (is_owner(org_id));

create policy projects_read on projects for select using (can(id, 'view'));
create policy projects_levers on projects for update using (can(id, 'change_levers')) with check (can(id, 'change_levers'));
create policy projects_create on projects for insert with check (is_owner(org_id));
create policy projects_delete on projects for delete using (is_owner(org_id));

create policy grants_read on grants for select using (user_id = auth.uid() or can(project_id, 'manage_access'));
create policy grants_write on grants for all using (can(project_id, 'manage_access')) with check (can(project_id, 'manage_access'));

create policy runs_read on runs for select using (can(project_id, 'view'));   -- inserts come from the service role only

create policy audit_read on audit for select using (is_owner(org_id));        -- inserts: service role only; no update/delete policy
revoke update, delete on audit from public;
