-- One MCP security engine, and a scan that describes running a server rather
-- than analysing a repository.
--
-- APPLY THIS *AFTER* THE NEW API IS DEPLOYED, NOT BEFORE.
--
-- This is the one migration in this directory where the order is not a
-- preference. It drops columns the previous API reads on its hot paths
-- (mcp_detection_confidence, mcp_capabilities, findings.verified and the
-- rest), so running it against a host still serving the old image takes the
-- dashboard down immediately - the same generic "Upstream data store error"
-- that migration 0046 produced when five column projections were left behind,
-- and for exactly the same reason in the opposite direction.
--
-- The safe sequence:
--   1. deploy-backend succeeds and the new image is live and healthy
--   2. apply this file
--   3. rescan the catalogue (POST /admin/marketplace/mcp/regrade-ungraded)
--
-- Between 1 and 2 the new API reads none of these columns, so the window is
-- safe in that direction. There is no safe window the other way round.
--
-- The columns dropped here all described the old source-analysis pipeline.
-- They are not being tidied away on suspicion: each one was written by a
-- module that no longer exists, and nothing reads them.
--
--   mcp_detection_confidence / mcp_detection_evidence
--       produced by analysis/mcp_detection.py, which guessed whether a
--       repository contained an MCP server by looking for SDK imports. The
--       question no longer arises: either the server starts and returns
--       tools, or the scan is incomplete and says so.
--   mcp_components
--       which sub-directories of a monorepo looked like separate servers.
--       A launch command resolves to exactly one server.
--   mcp_capabilities
--       a summary of permissions inferred from source. The engine reports
--       per-tool behaviour from the live tool definitions instead.
--
-- `scan_stages.name` changes completely, and the rows have to go before the
-- constraint is added rather than after - `add constraint ... check`
-- validates existing rows the moment it is added, which is how migration
-- 0046's first attempt failed. Retired stage rows are deleted first.
--
-- Every statement here is written to be safe to re-run: the DDL is guarded
-- with if exists / if not exists, and each UPDATE carries a WHERE so a second
-- run rewrites no rows. A migration that has to be applied by hand will be
-- applied by hand twice sooner or later.
--
-- Historical scans are deliberately left in place with their findings. What
-- they lose is the ability to claim a grade under the current model, exactly
-- as 0046 did: a scan produced by a different engine is not comparable to one
-- produced by this one, and quietly presenting it as if it were would be a
-- lie about a security result.

-- ---------------------------------------------------------------- scans

-- What was actually run, so a result can be reproduced and a resolution
-- mistake stays visible. A grade attributed to the wrong package is the
-- failure the resolver exists to prevent; this is where it can be caught
-- after the fact.
alter table public.scans add column if not exists server_command text;
alter table public.scans add column if not exists scanner_name text;
alter table public.scans add column if not exists scanner_version text;
alter table public.scans add column if not exists invocation_channel text;

alter table public.scans drop constraint if exists scans_invocation_channel_check;
alter table public.scans add constraint scans_invocation_channel_check
  check (
    invocation_channel is null
    or invocation_channel in ('dashboard', 'cli', 'hook', 'ci', 'mcp', 'marketplace')
  );

alter table public.scans drop column if exists mcp_detection_confidence;
alter table public.scans drop column if exists mcp_detection_evidence;
alter table public.scans drop column if exists mcp_components;
alter table public.scans drop column if exists mcp_capabilities;

-- A scan graded under the previous engine cannot be compared with one graded
-- under this one. The findings stay - they are still real evidence, and the
-- report still renders them - but the letter and the number are withdrawn
-- rather than reinterpreted.
update public.scans set grade = null, risk_score = null
where grade is not null or risk_score is not null;

-- ---------------------------------------------------------- scan_stages

alter table public.scan_stages drop constraint if exists scan_stages_name_check;

-- Order matters: the constraint below validates every existing row at the
-- moment it is added, so rows naming a retired stage have to go first or the
-- ADD aborts and takes the transaction with it.
delete from public.scan_stages
where name not in ('resolving', 'launching', 'enumerating', 'analyzing', 'grading');

alter table public.scan_stages add constraint scan_stages_name_check
  check (name in ('resolving', 'launching', 'enumerating', 'analyzing', 'grading'));

-- ----------------------------------------------------------- hook_cache

-- Same reasoning as scans: a cached letter from the previous engine would be
-- served to the Claude Code hook as a current verdict.
update public.hook_cache set last_grade = null, last_risk_score = null
where last_grade is not null or last_risk_score is not null;

-- ---------------------------------------------------------- marketplace

-- Listings keep their rows and their history; they lose the grade until they
-- are rescanned by the current engine. `current_trust_grade` going null puts
-- them in the "not yet scanned" state the catalogue already renders honestly.
update public.mcp_listings set current_trust_grade = null, current_risk_score = null
where current_trust_grade is not null or current_risk_score is not null;
update public.mcp_listing_versions set trust_grade = null, risk_score = null
where trust_grade is not null or risk_score is not null;

-- --------------------------------------------------- rug_pull_signatures

-- Tool-set drift between scans was Aevrin's own check, and the module that
-- computed it is gone. The table has no writer and no reader left; dropping
-- it is the honest end state rather than leaving a table that quietly stops
-- being maintained.
drop table if exists public.rug_pull_signatures;

-- ------------------------------------------------------------- findings

-- CVE-enrichment columns, dropped with the repository-wide dependency
-- scanning that produced them. EPSS probabilities and CISA KEV membership
-- describe a CVE in a dependency tree; the engine's supply-chain rules are
-- scoped to the scanned server's own dependencies and carry their evidence
-- in `evidence` like every other finding. `corroborated_by` recorded two
-- scanners agreeing, which cannot happen with one engine.
alter table public.findings drop column if exists epss_score;
alter table public.findings drop column if exists in_kev;
alter table public.findings drop column if exists dependency_scope;
alter table public.findings drop column if exists corroborated_by;
alter table public.findings drop column if exists original_severity;

-- The last of the producerless finding columns. Each was written by a module
-- deleted with the old pipeline:
--   verified        TruffleHog's live credential verification
--   mcp_tool        source attribution of a finding to a tool's function body
--   capability      the taint pack's sink vocabulary
--   confidence      a post-processing severity adjustment
--   not_tested      the synthetic MCP08 coverage placeholder
--   excluded_path   fixture/test path exclusion
--
-- The last two are worth naming: a finding now describes a tool a live server
-- returned, so there is no file path for it to sit under a `tests/` directory,
-- and no placeholder row to keep out of the counts. Triage is the only reason
-- left that a finding is shown but not counted.
alter table public.findings drop column if exists verified;
alter table public.findings drop column if exists mcp_tool;
alter table public.findings drop column if exists capability;
alter table public.findings drop column if exists confidence;
alter table public.findings drop column if exists not_tested;
alter table public.findings drop column if exists excluded_path;
