-- Admin control panel foundations.
--
-- Read alongside docs/ADMIN_PANEL_PLAN.md. Every table here backs a control
-- that can affect a paying customer, so each one is either append-only or
-- carries who-changed-it provenance.

-- ---------------------------------------------------------------- audit log
--
-- Append-only by grant, not by convention. The app's role gets INSERT and
-- SELECT and nothing else, so a bug (or a compromised app credential) cannot
-- quietly rewrite history. Deliberately not a foreign key on target_user_id:
-- the log must survive the account it describes being deleted, otherwise the
-- record of a deletion disappears with the thing it recorded.
create table if not exists public.admin_audit_log (
  id bigserial primary key,
  actor_user_id uuid not null,
  actor_email text,
  action text not null,
  target_user_id uuid,
  target_email text,
  target_resource text,
  reason text,
  metadata jsonb not null default '{}'::jsonb,
  ip_address text,
  user_agent text,
  created_at timestamptz not null default now()
);

create index if not exists admin_audit_log_created_idx on public.admin_audit_log (created_at desc);
create index if not exists admin_audit_log_actor_idx on public.admin_audit_log (actor_user_id, created_at desc);
create index if not exists admin_audit_log_target_idx on public.admin_audit_log (target_user_id, created_at desc);
create index if not exists admin_audit_log_action_idx on public.admin_audit_log (action, created_at desc);

comment on table public.admin_audit_log is
  'Append-only record of every admin action. No UPDATE/DELETE grants; see the revokes at the bottom of this migration.';

-- ------------------------------------------------------------ account state
--
-- There is currently NO account-status check anywhere in the auth chain
-- (deps.get_current_user only decodes the JWT; get_api_key_user only checks
-- the key's own revoked_at). This column is inert until that enforcement
-- lands; see Phase A3 in the plan.
--
-- 'disabled' is the reversible support action; 'blocked' is the abuse action
-- that additionally feeds the fingerprint layer.
alter table public.accounts
  add column if not exists status text not null default 'active'
    check (status in ('active', 'disabled', 'blocked')),
  add column if not exists status_reason text,
  add column if not exists status_changed_at timestamptz,
  add column if not exists status_changed_by uuid;

create index if not exists accounts_status_idx on public.accounts (status) where status <> 'active';

comment on column public.accounts.status is
  'active | disabled (reversible support action) | blocked (abuse; also flags the account signals). Enforced in the API auth chain and the web proxy.';

-- The product sells Pro and tier_limits has a pro row, but this CHECK never
-- included it; an admin plan change to Pro would have failed on write.
alter table public.accounts drop constraint if exists accounts_tier_check;
alter table public.accounts
  add constraint accounts_tier_check check (tier in ('free', 'hobby', 'pro', 'team'));

-- -------------------------------------------------------- quota overrides
--
-- Consulted by quota._tier_limit() *before* falling back to the plan default,
-- so an override applies to every caller (dashboard, CLI, hook) rather than
-- only the surface an admin happened to be looking at.
--
-- limit_value NULL means "unlimited for this bucket", the same convention
-- tier_limits already uses, so the override layer needs no special case.
create table if not exists public.account_quota_overrides (
  user_id uuid not null references auth.users (id) on delete cascade,
  bucket text not null check (bucket in ('cli', 'hook', 'dashboard', 'auto_fix')),
  limit_value integer,
  expires_at timestamptz,
  reason text,
  created_by uuid,
  created_at timestamptz not null default now(),
  primary key (user_id, bucket)
);

comment on table public.account_quota_overrides is
  'Per-account per-bucket limit overrides. NULL limit_value = unlimited. Expired rows are ignored at read time rather than deleted, so the history stays visible.';

-- ------------------------------------------------------------- admin TOTP
--
-- Secret is stored encrypted with the same Fernet key the BYOK path uses
-- (crypto.py); never in plaintext, and never rendered back to the UI after
-- enrolment.
create table if not exists public.admin_totp (
  user_id uuid primary key references auth.users (id) on delete cascade,
  encrypted_secret text not null,
  confirmed_at timestamptz,
  last_used_step bigint,
  created_at timestamptz not null default now()
);

comment on column public.admin_totp.last_used_step is
  'Last accepted TOTP time-step. Stored to reject replay of a code inside its own validity window.';

-- ----------------------------------------------------- admin notifications
create table if not exists public.admin_notifications (
  id bigserial primary key,
  kind text not null,
  severity text not null default 'info' check (severity in ('info', 'warning', 'critical')),
  title text not null,
  body text,
  metadata jsonb not null default '{}'::jsonb,
  read_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists admin_notifications_unread_idx
  on public.admin_notifications (created_at desc) where read_at is null;

-- --------------------------------------------------------- daily rollups
--
-- The analytics home must not scan raw scans/findings on every page load.
-- One row per day, recomputed by a scheduled job; `metrics` is jsonb so a new
-- measure doesn't need a migration.
create table if not exists public.analytics_daily (
  day date primary key,
  metrics jsonb not null default '{}'::jsonb,
  computed_at timestamptz not null default now()
);

-- ------------------------------------------------------------ admin logins
--
-- Failed admin logins are a signal worth surfacing, so they are recorded
-- separately from the audit log (which is for actions that succeeded).
create table if not exists public.admin_login_attempts (
  id bigserial primary key,
  user_id uuid,
  email text,
  succeeded boolean not null,
  failure_reason text,
  ip_address text,
  user_agent text,
  created_at timestamptz not null default now()
);

create index if not exists admin_login_attempts_recent_idx
  on public.admin_login_attempts (created_at desc);

-- ------------------------------------------------------------------- RLS
--
-- Every one of these is reached only through the service role in the API,
-- never from a browser client, so RLS is enabled with no permissive policy:
-- deny-by-default for anon/authenticated, service role bypasses.
alter table public.admin_audit_log enable row level security;
alter table public.account_quota_overrides enable row level security;
alter table public.admin_totp enable row level security;
alter table public.admin_notifications enable row level security;
alter table public.analytics_daily enable row level security;
alter table public.admin_login_attempts enable row level security;

-- ------------------------------------------------- append-only enforcement
--
-- The audit log's whole value is that it cannot be edited after the fact.
-- Revoking UPDATE/DELETE from the roles the app can act as makes that a
-- database guarantee rather than a code convention. The service role used by
-- the API is a superuser-equivalent in Supabase and bypasses this, which is
-- why Phase A9's verification attempts the modification through the app's
-- own path and confirms refusal.
revoke update, delete on public.admin_audit_log from anon, authenticated;
revoke update, delete on public.admin_login_attempts from anon, authenticated;

-- A trigger is the backstop that also covers the service role.
create or replace function public.admin_audit_log_immutable()
returns trigger
language plpgsql
as $$
begin
  raise exception 'admin_audit_log is append-only (attempted %)', tg_op;
end;
$$;

drop trigger if exists admin_audit_log_no_update on public.admin_audit_log;
create trigger admin_audit_log_no_update
  before update or delete on public.admin_audit_log
  for each row execute function public.admin_audit_log_immutable();
