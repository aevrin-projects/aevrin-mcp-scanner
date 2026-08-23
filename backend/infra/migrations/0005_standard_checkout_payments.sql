-- One-time-payment billing (Razorpay Standard Checkout / Orders API),
-- replacing the Subscriptions-based auto-recurring flow from 0003: paying
-- activates a tier through accounts.paid_until. Nothing charges
-- automatically again after that expires; the account is expected to pay
-- again for the next cycle (explicit user decision: no auto-recurring
-- charges "for now").
alter table public.accounts add column if not exists paid_until timestamptz;

create table if not exists public.payments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  tier text not null check (tier in ('hobby', 'team')),
  cycle text not null check (cycle in ('monthly', 'annual')),
  amount_paise integer not null,
  currency text not null default 'INR',
  razorpay_order_id text not null unique,
  razorpay_payment_id text,
  razorpay_signature text,
  status text not null default 'created' check (status in ('created', 'paid', 'failed')),
  created_at timestamptz not null default now(),
  verified_at timestamptz
);

create index if not exists payments_user_id_idx on public.payments (user_id);

alter table public.payments enable row level security;

create policy payments_owner_select on public.payments for select to authenticated
  using (user_id = (select auth.uid()));
