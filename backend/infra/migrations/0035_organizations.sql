-- Organizations: a shared workspace with roles its owner defines.
--
-- Until now an account was one person, and the Team plan sold seats that were
-- a billing quantity and nothing else. This makes a workspace real: members
-- see the same scans, agents and findings, and what each member may do is
-- decided by a role the workspace owner writes.
--
-- A person belongs to at most one organization. That is the whole reason this
-- stays small: no workspace switcher, no "which org is this request about",
-- and every existing query grows one OR rather than a join. If someone ever
-- needs two, they need two logins, and that is a trade worth taking over
-- making every table in the product ambiguous.

create table if not exists public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(trim(name)) between 1 and 80),
  -- Kept as a column rather than derived from a role: the owner is who the
  -- account belongs to, survives every role edit, and is the one member no
  -- permission change can lock out.
  owner_id uuid not null references auth.users (id) on delete cascade,
  -- What the Team plan was already charging for. Enforced when adding a
  -- member, not retroactively: reducing seats must never silently eject
  -- somebody who is in the middle of their work.
  seats integer not null default 3 check (seats between 1 and 500),
  created_at timestamptz not null default now()
);

create unique index if not exists organizations_owner_idx on public.organizations (owner_id);

-- A role is a name and a set of permission strings. Not a policy language:
-- the catalogue of permissions is fixed in the API, the owner chooses which
-- of them a role holds, and anything not held is refused.
create table if not exists public.organization_roles (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations (id) on delete cascade,
  name text not null check (length(trim(name)) between 1 and 40),
  permissions text[] not null default '{}',
  -- The one role that cannot be edited, deleted, or stripped of anything.
  -- Without it a workspace could be locked out of its own administration by
  -- an owner editing their way into a role that cannot manage roles.
  is_owner_role boolean not null default false,
  created_at timestamptz not null default now(),
  unique (org_id, name)
);

create index if not exists organization_roles_org_idx on public.organization_roles (org_id);

create table if not exists public.organization_members (
  org_id uuid not null references public.organizations (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  role_id uuid not null references public.organization_roles (id) on delete restrict,
  joined_at timestamptz not null default now(),
  primary key (org_id, user_id)
);

-- One workspace per person, enforced here rather than in application code so
-- a concurrent double-accept cannot produce two memberships.
create unique index if not exists organization_members_one_org_idx
  on public.organization_members (user_id);

-- Invites are addressed to an email, because the person may not have an
-- account yet. Nothing is granted until they accept while signed in, so an
-- invite to an address someone else controls grants that someone nothing
-- until they prove they hold the address by signing in with it.
create table if not exists public.organization_invites (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations (id) on delete cascade,
  email text not null check (position('@' in email) > 1),
  role_id uuid not null references public.organization_roles (id) on delete cascade,
  invited_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  accepted_at timestamptz,
  unique (org_id, email)
);

create index if not exists organization_invites_email_idx on public.organization_invites (lower(email));

-- --------------------------------------------------------------------------
-- Membership helpers
--
-- SECURITY DEFINER so RLS on the tables below can ask "is the caller in this
-- org" without the caller needing to be able to read the membership table
-- directly, and without the recursion that a policy querying its own table
-- would produce.

create or replace function public.is_org_member(p_org uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.organization_members
    where org_id = p_org and user_id = (select auth.uid())
  );
$$;

create or replace function public.my_org()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select org_id from public.organization_members where user_id = (select auth.uid());
$$;

-- --------------------------------------------------------------------------
-- Shared work
--
-- org_id is nullable and starts null: a row with no org is personal, exactly
-- as every row is today. Setting it is what shares it. `on delete set null`
-- rather than cascade, because deleting a workspace must not delete the scan
-- history of the people who were in it.

alter table public.scans add column if not exists org_id uuid references public.organizations (id) on delete set null;
alter table public.findings add column if not exists org_id uuid references public.organizations (id) on delete set null;
alter table public.agent_snapshots add column if not exists org_id uuid references public.organizations (id) on delete set null;

create index if not exists scans_org_idx on public.scans (org_id, created_at desc);
create index if not exists findings_org_idx on public.findings (org_id);
create index if not exists agent_snapshots_org_idx on public.agent_snapshots (org_id);

-- Visible if it is mine, or if it belongs to a workspace I am in. Replacing
-- rather than adding a policy: two permissive policies OR together, which
-- would be the same result by a route that is harder to read later.
drop policy if exists scans_owner_select on public.scans;
create policy scans_owner_select on public.scans for select to authenticated
  using (user_id = (select auth.uid()) or (org_id is not null and public.is_org_member(org_id)));

drop policy if exists findings_owner_select on public.findings;
create policy findings_owner_select on public.findings for select to authenticated
  using (user_id = (select auth.uid()) or (org_id is not null and public.is_org_member(org_id)));

drop policy if exists scan_stages_owner_select on public.scan_stages;
create policy scan_stages_owner_select on public.scan_stages for select to authenticated
  using (exists (
    select 1 from public.scans s
    where s.id = scan_id
      and (s.user_id = (select auth.uid()) or (s.org_id is not null and public.is_org_member(s.org_id)))
  ));

drop policy if exists agent_snapshots_owner_select on public.agent_snapshots;
create policy agent_snapshots_owner_select on public.agent_snapshots for select to authenticated
  using (user_id = (select auth.uid()) or (org_id is not null and public.is_org_member(org_id)));

-- Deletes and updates stay with the row's owner. Reading a colleague's scan
-- is the point of a shared workspace; deleting it out from under them is not,
-- and the API refuses it too rather than relying on this alone.

-- --------------------------------------------------------------------------
-- The workspace's own tables
--
-- Members read; every write goes through the API's service role, which is
-- what makes a permission check something a member cannot bypass by talking
-- to PostgREST directly.

alter table public.organizations enable row level security;
alter table public.organization_roles enable row level security;
alter table public.organization_members enable row level security;
alter table public.organization_invites enable row level security;

create policy organizations_member_select on public.organizations for select to authenticated
  using (public.is_org_member(id));

create policy organization_roles_member_select on public.organization_roles for select to authenticated
  using (public.is_org_member(org_id));

create policy organization_members_member_select on public.organization_members for select to authenticated
  using (public.is_org_member(org_id));

-- An invitee is not a member yet, so they could not otherwise see the invite
-- addressed to them. Matched on the email in their own JWT.
create policy organization_invites_visible on public.organization_invites for select to authenticated
  using (
    public.is_org_member(org_id)
    or lower(email) = lower(coalesce((select auth.jwt() ->> 'email'), ''))
  );

comment on table public.organization_invites is
  'Invites carry no secret. Acceptance requires being signed in as the invited address.';

-- --------------------------------------------------------------------------
-- Member emails
--
-- auth.users is not reachable through the Data API, and asking for one
-- identity per member would be a query per row on a page whose whole job is
-- to list them. One call, and only for a workspace the caller is in.

create or replace function public.org_member_emails(p_org uuid)
returns table (user_id uuid, email text)
language sql
stable
security definer
set search_path = public, auth, pg_temp
as $$
  select m.user_id, u.email::text
  from public.organization_members m
  join auth.users u on u.id = m.user_id
  where m.org_id = p_org
    and exists (
      select 1 from public.organization_members me
      where me.org_id = p_org and me.user_id = (select auth.uid())
    );
$$;

revoke all on function public.org_member_emails(uuid) from public, anon;
grant execute on function public.org_member_emails(uuid) to authenticated, service_role;

-- --------------------------------------------------------------------------
-- New work joins the workspace automatically
--
-- Every one of these tables already records whose row it is, so the workspace
-- can be derived from that rather than passed in by each caller. Doing it
-- here instead of at the five write sites means a write path added later
-- cannot forget, and it works for the API's service-role writes, where
-- auth.uid() is null and the trigger has nothing else to go on.
--
-- Only fills a null. A caller that sets org_id deliberately -- the move
-- performed when a workspace is created -- is left alone.

create or replace function public.stamp_org_id()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.org_id is null then
    select org_id into new.org_id
    from public.organization_members
    where user_id = new.user_id;
  end if;
  return new;
end;
$$;

drop trigger if exists scans_stamp_org on public.scans;
create trigger scans_stamp_org before insert on public.scans
  for each row execute function public.stamp_org_id();

drop trigger if exists findings_stamp_org on public.findings;
create trigger findings_stamp_org before insert on public.findings
  for each row execute function public.stamp_org_id();

drop trigger if exists agent_snapshots_stamp_org on public.agent_snapshots;
create trigger agent_snapshots_stamp_org before insert on public.agent_snapshots
  for each row execute function public.stamp_org_id();
