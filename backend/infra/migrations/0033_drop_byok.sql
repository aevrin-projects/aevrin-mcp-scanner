-- Bring-your-own-key is gone.
--
-- It was sold as a paid add-on, and the key it stored was never read by
-- anything: triage always used the pooled provider key, so a customer paid a
-- monthly fee for a credential this server held and never called. Holding a
-- secret with no purpose is a liability, not a feature.
--
-- Dropping the columns is the point of this migration rather than a side
-- effect: the ciphertext goes with them.

alter table public.accounts
  drop column if exists byok_enabled,
  drop column if exists byok_provider,
  drop column if exists byok_key_encrypted;

-- `payments.byok` was a per-order flag on a product that no longer exists.
alter table public.payments drop column if exists byok;

-- Neither add-on can be purchased any more. The historical tiers stay in the
-- constraint because rows carrying them may be re-verified by a browser, and
-- the API still has to recognise them to guarantee an add-on never extends a
-- subscription -- see billing_controller.verify_payment.
