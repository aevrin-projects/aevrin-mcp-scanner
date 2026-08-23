-- BYOK could only be obtained by buying a whole plan cycle with the byok
-- flag set. Someone already on a paid plan had no way to add it without
-- purchasing another cycle, so the billing page's add-on card bounced them
-- to the pricing page instead of taking the payment.
--
-- byok_enabled is a boolean on the account with no expiry, so a standalone
-- one-time purchase fits the existing model exactly: pay the flat platform
-- fee, the flag is set, it stays set.
alter table public.payments drop constraint if exists payments_tier_check;
alter table public.payments add constraint payments_tier_check
  check (tier in ('hobby', 'pro', 'team', 'autofix_addon', 'byok_addon'));
