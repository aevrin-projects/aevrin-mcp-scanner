-- The registry is discovery only: drop the marketplace's own scanning state.
--
-- CONTRACT MIGRATION. APPLY ONLY AFTER THE NEW API IMAGE IS DEPLOYED AND
-- HEALTHY. NEVER BEFORE.
--
-- Every statement here removes something. The API image deployed before this
-- change still selects these columns on every browse, detail and admin read
-- (`current_trust_grade` and friends in the catalogue projection,
-- `scan_id` on the version rows, `org_mcp_policies` in the install plan), so
-- applying this first takes the registry and the admin registry page down
-- until the new image ships. The new image reads none of them, so the order
-- that works is:
--   1. deploy the backend and the frontend; wait for /health on the new image
--   2. apply this file
-- The window between 1 and 2 is safe: the new API ignores these columns, and
-- the old values simply sit unread until they are dropped.
--
-- What goes, and why (DECISIONS.md, the "registry is discovery only" ADR):
--
--   mcp_listings.current_*            the cached grade projection. Nothing
--                                     writes it (grading.py is deleted) and
--                                     nothing reads it.
--   mcp_listing_versions scan columns a version row is now a bare record of a
--                                     version the registry has seen: id,
--                                     listing_id, version, first_seen_at.
--                                     The scan reference, grade, score,
--                                     coverage, provenance and the package
--                                     fields that only chose what to launch
--                                     for a catalogue scan are dropped.
--   org_mcp_policies                  the per-grade install policy. With no
--                                     grade on any item there is nothing for
--                                     it to decide.
--   tier_limits.marketplace_policies  the entitlement for that policy.
--   ai_explanations 'trust_grade' and 'listing'
--                                     cached explanations of a listing's
--                                     grade. Explanations now attach to a
--                                     user's own scan ('scan', 'finding').
--
-- Deliberately left alone: the scans rows the old catalogue scans produced
-- (a scan is evidence that belongs to the account that ran it),
-- `scans.invocation_channel` still accepting 'marketplace' (historic rows
-- carry it), and `mcp_events.event_type` still accepting 'scan_completed'
-- and 'grade_changed' (historic timeline rows; the UI hides them).
--
-- Idempotent: every drop is `if exists`, so re-running it is a no-op.

-- ----------------------------------------------------------- mcp_listings

drop index if exists public.mcp_listings_grade_idx;

alter table public.mcp_listings drop constraint if exists mcp_listings_current_trust_grade_check;
alter table public.mcp_listings drop constraint if exists mcp_listings_current_risk_score_check;
alter table public.mcp_listings drop constraint if exists mcp_listings_current_security_score_check;

alter table public.mcp_listings drop column if exists current_version;
alter table public.mcp_listings drop column if exists current_trust_grade;
alter table public.mcp_listings drop column if exists current_risk_score;
alter table public.mcp_listings drop column if exists current_coverage_complete;
alter table public.mcp_listings drop column if exists current_scanned_at;

comment on table public.mcp_listings is
  'The Aevrin Registry: every catalogued capability, of every item_type. Discovery only: no scan result or grade is stored here or on mcp_listing_versions. Users scan a server themselves through the scans API.';

-- --------------------------------------------------- mcp_listing_versions

alter table public.mcp_listing_versions drop constraint if exists mcp_listing_versions_trust_grade_check;
alter table public.mcp_listing_versions drop constraint if exists mcp_listing_versions_risk_score_check;
alter table public.mcp_listing_versions drop constraint if exists mcp_listing_versions_scan_id_fkey;

alter table public.mcp_listing_versions drop column if exists scan_id;
alter table public.mcp_listing_versions drop column if exists trust_grade;
alter table public.mcp_listing_versions drop column if exists risk_score;
alter table public.mcp_listing_versions drop column if exists coverage_complete;
alter table public.mcp_listing_versions drop column if exists scanner_versions;
alter table public.mcp_listing_versions drop column if exists scan_status;
alter table public.mcp_listing_versions drop column if exists scanned_at;
alter table public.mcp_listing_versions drop column if exists source_hash;
alter table public.mcp_listing_versions drop column if exists package_registry;
alter table public.mcp_listing_versions drop column if exists package_identifier;

-- ------------------------------------------------------ install policy

-- Its RLS policy goes with it.
drop table if exists public.org_mcp_policies;

alter table public.tier_limits drop column if exists marketplace_policies;

-- ---------------------------------------------------- AI explanations

delete from public.ai_explanations where subject_type in ('trust_grade', 'listing');

alter table public.ai_explanations drop constraint if exists ai_explanations_subject_type_check;
alter table public.ai_explanations add constraint ai_explanations_subject_type_check
  check (subject_type in (
    'finding', 'agent_posture', 'permission', 'skill', 'attack_path', 'scan'
  ));
