-- Four-tier pricing (AEVRIN_ACCURACY_PRICING_PROMPT.md addendum §3), kept on
-- Razorpay's existing one-time-per-cycle checkout — no payment processor
-- migration. Adds a 'pro' tier between hobby and team, and a `seats` column
-- so team billing can charge per-seat (3-seat minimum) while the account
-- itself stays the single row per auth.users id it already is — seats are a
-- billing quantity, not a new multi-user access model.

alter table public.accounts drop constraint if exists accounts_tier_check;
alter table public.accounts add constraint accounts_tier_check check (tier in ('free', 'hobby', 'pro', 'team'));

alter table public.accounts add column if not exists seats integer not null default 1 check (seats >= 1);

alter table public.tier_limits drop constraint if exists tier_limits_tier_check;
alter table public.tier_limits add constraint tier_limits_tier_check check (tier in ('free', 'hobby', 'pro', 'team'));

insert into public.tier_limits (tier, cli_scans_per_month, hook_scans_per_month, dashboard_scans_per_month, history_retention_days, pdf_export, seats_included)
values
  ('pro', 200, 100, 200, 365, true, 1)
on conflict (tier) do update set
  cli_scans_per_month = excluded.cli_scans_per_month,
  hook_scans_per_month = excluded.hook_scans_per_month,
  dashboard_scans_per_month = excluded.dashboard_scans_per_month,
  history_retention_days = excluded.history_retention_days,
  pdf_export = excluded.pdf_export,
  seats_included = excluded.seats_included;

alter table public.payments drop constraint if exists payments_tier_check;
alter table public.payments add constraint payments_tier_check check (tier in ('hobby', 'pro', 'team'));

alter table public.payments add column if not exists seats integer not null default 1 check (seats >= 1);
alter table public.payments add column if not exists byok boolean not null default false;

-- BYOK (bring-your-own-key triage): +$3/mo add-on on any paid tier, or
-- included at no extra charge for team (reduces Aevrin's model spend, so
-- it's a discount lever there rather than an upsell). The key itself is
-- never stored in plaintext: byok_key_encrypted holds Fernet ciphertext
-- (apps/api/src/aevrin_api/crypto.py), encrypted/decrypted at the app layer
-- with BYOK_ENCRYPTION_KEY (a server-only env var), not in Postgres —
-- pgsodium isn't installed on this project and Vault would need a new RPC
-- surface this app doesn't otherwise use, so app-layer envelope encryption
-- matches how every other secret in this codebase is handled (Settings-held
-- env vars), not a new pattern.
alter table public.accounts add column if not exists byok_enabled boolean not null default false;
alter table public.accounts add column if not exists byok_provider text check (byok_provider in ('anthropic', 'google'));
alter table public.accounts add column if not exists byok_key_encrypted text;
