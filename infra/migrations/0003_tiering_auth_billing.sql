-- Tiering, device-flow auth, and billing metadata (AEVRIN_TIERING_AUTH_LANDING_PROMPT.md addendum).
-- Mirrors what's applied to Supabase via the MCP `execute_sql` tool during
-- development; kept in-repo so schema history is reviewable outside the
-- Supabase dashboard, same convention as 0001_init.sql / 0002.

-- accounts: tier/billing metadata per Supabase user. Not a new identity
-- system — one row per auth.users id, created lazily on first login.
create table if not exists public.accounts (
  user_id uuid primary key references auth.users (id) on delete cascade,
  tier text not null default 'free' check (tier in ('free', 'hobby', 'team')),
  -- rolling monthly reset anchor (day of month the account signed up),
  -- clamped to 1-28 to sidestep month-length edge cases (addendum: "rolling
  -- monthly cycle from the account's signup date", not calendar month).
  signup_anchor_day integer not null check (signup_anchor_day between 1 and 28),
  razorpay_customer_id text,
  razorpay_subscription_id text,
  subscription_status text,
  flagged boolean not null default false,
  downgrade_effective_at timestamptz,
  created_at timestamptz not null default now()
);

-- device_codes: RFC 8628 device authorization grant state, used by both the
-- CLI's `aevrin login` and the hook's setup flow.
create table if not exists public.device_codes (
  device_code text primary key,
  user_code text not null unique,
  status text not null default 'pending' check (status in ('pending', 'approved', 'denied', 'expired')),
  user_id uuid references auth.users (id) on delete cascade,
  client_kind text not null check (client_kind in ('cli', 'hook')),
  machine_id_hash text,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

create index if not exists device_codes_user_code_idx on public.device_codes (user_code);
create index if not exists device_codes_expires_at_idx on public.device_codes (expires_at);

-- abuse_signals: append-only. Read by a "2+ matching signals" rule
-- server-side (flag, never hard-block on a single signal — addendum §4).
create table if not exists public.abuse_signals (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  signal_type text not null check (signal_type in ('fingerprint', 'machine_id', 'ip_velocity')),
  value_hash text not null,
  created_at timestamptz not null default now()
);

create index if not exists abuse_signals_value_hash_idx on public.abuse_signals (signal_type, value_hash);
create index if not exists abuse_signals_user_id_idx on public.abuse_signals (user_id);

-- tier_limits: config table, not hardcoded (addendum §1: "they live in
-- Stripe and a config table, not hardcoded"). Read by both the quota engine
-- and the public pricing page. null in a *_per_month or retention column
-- means unlimited (Team tier).
create table if not exists public.tier_limits (
  tier text primary key check (tier in ('free', 'hobby', 'team')),
  cli_scans_per_month integer,
  hook_scans_per_month integer,
  dashboard_scans_per_month integer,
  history_retention_days integer,
  pdf_export boolean not null default false,
  seats_included integer not null default 1
);

insert into public.tier_limits (tier, cli_scans_per_month, hook_scans_per_month, dashboard_scans_per_month, history_retention_days, pdf_export, seats_included)
values
  ('free', 5, 2, 5, 7, false, 1),
  ('hobby', 50, 20, 50, 90, true, 1),
  ('team', null, null, null, null, true, 5)
on conflict (tier) do update set
  cli_scans_per_month = excluded.cli_scans_per_month,
  hook_scans_per_month = excluded.hook_scans_per_month,
  dashboard_scans_per_month = excluded.dashboard_scans_per_month,
  history_retention_days = excluded.history_retention_days,
  pdf_export = excluded.pdf_export,
  seats_included = excluded.seats_included;

-- Distinguishes dashboard-issued keys from device-flow-issued CLI/hook
-- tokens, reusing the existing api_keys table/hashing rather than a
-- parallel token system.
alter table public.api_keys add column if not exists kind text not null default 'manual' check (kind in ('manual', 'device_cli', 'device_hook'));

-- RLS: accounts/abuse_signals owner-scoped, same (select auth.uid()) pattern
-- as 0001_init.sql. device_codes has no client-facing policies — the
-- /device page looks up by user_code, not ownership, before a row even has
-- a user_id, and all device_codes writes go through the api service's
-- service-role key (which bypasses RLS). tier_limits is public-readable
-- since the pricing page needs it unauthenticated.

alter table public.accounts enable row level security;
alter table public.device_codes enable row level security;
alter table public.abuse_signals enable row level security;
alter table public.tier_limits enable row level security;

create policy accounts_owner_select on public.accounts for select to authenticated
  using (user_id = (select auth.uid()));

create policy abuse_signals_owner_select on public.abuse_signals for select to authenticated
  using (user_id = (select auth.uid()));

create policy tier_limits_public_select on public.tier_limits for select to authenticated, anon
  using (true);
