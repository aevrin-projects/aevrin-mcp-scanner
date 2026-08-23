-- Auto-fix funding (AEVRIN_CONSOLIDATED_V5_PROMPT.md §5/§7). Pro/Team price
-- bump funds a bundled monthly PR allowance; a Pro/Team-only add-on tops it
-- up. Bonus PRs are cumulative, not reset per rolling period, a purchased
-- top-up isn't forfeited just because it wasn't fully used inside 30 days.
alter table public.tier_limits add column if not exists auto_fix_prs_per_month integer not null default 0;
alter table public.accounts add column if not exists auto_fix_bonus_prs integer not null default 0 check (auto_fix_bonus_prs >= 0);

update public.tier_limits set auto_fix_prs_per_month = 15 where tier in ('pro', 'team');

-- Auto-fix add-on purchases reuse the payments table (same Razorpay
-- Standard Checkout flow as a tier purchase) rather than a parallel table;
-- 'autofix_addon' is a payments-only pseudo-tier; it's never a valid value
-- for accounts.tier or tier_limits.tier, only for what a payment bought.
alter table public.payments drop constraint if exists payments_tier_check;
alter table public.payments add constraint payments_tier_check check (tier in ('hobby', 'pro', 'team', 'autofix_addon'));
