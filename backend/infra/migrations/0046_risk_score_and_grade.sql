-- Aevrin becomes an MCP-only security product, and the score changes
-- direction with it.
--
-- Two things happen here, and they have to happen together.
--
-- 1. `score` counted DOWN from 100 (higher was better). `risk_score` counts
--    UP from 0 (higher is worse). The two are not convertible: the severity
--    weights and the tier caps behind the old number are gone, so
--    `100 - score` would be a fabricated value, not a migration. Existing
--    rows are therefore set to NULL rather than arithmetic-converted, and
--    the column is renamed so nothing can silently read the old meaning out
--    of the new name. A historical scan reads as "not scored under the
--    current model", which is true, instead of as its own inverse, which
--    would be a lie about a security result.
--
-- 2. Grades gain 'F' and gain NULL. NULL is not "missing" - it is the state
--    of a scan whose MCP tools could not be enumerated, where a letter would
--    be a claim about evidence nobody has. See mcp/risk.py.
--
-- Also drops the code/MCP/dependency sub-scores. They described a
-- code-security product that no longer exists, and nothing user-facing read
-- them; the finding list, where every finding now carries a rule id and its
-- own evidence, answers "what earned this grade" better than three opaque
-- numbers did.

-- ---------------------------------------------------------------- scans

alter table public.scans rename column score to risk_score;
alter table public.scans drop constraint if exists scans_score_check;
alter table public.scans add constraint scans_risk_score_check
  check (risk_score is null or risk_score between 0 and 100);

-- Not convertible; see the header. Blanked rather than guessed at.
update public.scans set risk_score = null;

alter table public.scans add column if not exists grade text;
alter table public.scans drop constraint if exists scans_grade_check;
alter table public.scans add constraint scans_grade_check
  check (grade is null or grade in ('A', 'B', 'C', 'D', 'F'));

-- The status set is unchanged, but 'incomplete' now also covers "tools could
-- not be read", which is the common case rather than the rare one.
alter table public.scans drop constraint if exists scans_status_check;
alter table public.scans add constraint scans_status_check
  check (status in ('queued', 'running', 'completed', 'failed', 'incomplete'));

-- ---------------------------------------------------------- scan_stages

-- static_analysis and tool_description_check are gone with the scanners
-- behind them; discovery, mcp_rules and mcp_behavior replace them.
--
-- Order matters here, and getting it wrong is how the first attempt at this
-- migration failed: `add constraint ... check` validates every existing row
-- at the moment it is added, not only on subsequent writes. Rows naming a
-- retired stage therefore have to go first, or the ADD aborts and takes the
-- whole transaction with it.
alter table public.scan_stages drop constraint if exists scan_stages_name_check;

-- Stage rows naming a stage that no longer exists mean nothing to a reader
-- and cannot satisfy the constraint below.
delete from public.scan_stages
where name not in (
  'cloning', 'discovery', 'mcp_rules', 'mcp_behavior',
  'secrets', 'dependencies', 'aggregating'
);

alter table public.scan_stages add constraint scan_stages_name_check
  check (
    name in (
      'cloning', 'discovery', 'mcp_rules', 'mcp_behavior',
      'secrets', 'dependencies', 'aggregating'
    )
  );

-- ------------------------------------------------------------- findings

-- Which rule produced this finding. `mcp/catalog.py` is the only place that
-- says what an id means, so a finding row carries the id and its evidence
-- and every renderer reads the prose from the catalogue - rewording a rule
-- never requires rewriting stored findings.
alter table public.findings add column if not exists rule_id text;
alter table public.findings add column if not exists evidence jsonb not null default '[]'::jsonb;
alter table public.findings add column if not exists affected_tools jsonb not null default '[]'::jsonb;

create index if not exists findings_scan_id_rule_id_idx
  on public.findings (scan_id, rule_id) where not not_tested;

-- ----------------------------------------------------------- hook_cache

alter table public.hook_cache rename column last_score to last_risk_score;
alter table public.hook_cache drop constraint if exists hook_cache_last_score_check;
alter table public.hook_cache add constraint hook_cache_last_risk_score_check
  check (last_risk_score is null or last_risk_score between 0 and 100);
update public.hook_cache set last_risk_score = null;

alter table public.hook_cache add column if not exists last_grade text;
alter table public.hook_cache drop constraint if exists hook_cache_last_grade_check;
alter table public.hook_cache add constraint hook_cache_last_grade_check
  check (last_grade is null or last_grade in ('A', 'B', 'C', 'D', 'F'));

-- ---------------------------------------------------------- marketplace

alter table public.mcp_listings rename column current_security_score to current_risk_score;
alter table public.mcp_listings drop constraint if exists mcp_listings_current_security_score_check;
alter table public.mcp_listings add constraint mcp_listings_current_risk_score_check
  check (current_risk_score is null or current_risk_score between 0 and 100);
update public.mcp_listings set current_risk_score = null;

alter table public.mcp_listings drop constraint if exists mcp_listings_current_trust_grade_check;
alter table public.mcp_listings add constraint mcp_listings_current_trust_grade_check
  check (current_trust_grade is null or current_trust_grade in ('A', 'B', 'C', 'D', 'F'));

drop index if exists mcp_listings_grade_idx;
-- Ascending risk beside ascending grade: "most secure first" now means the
-- smallest number, the opposite of what the old index ordered by.
create index if not exists mcp_listings_grade_idx
  on public.mcp_listings (current_trust_grade, current_risk_score asc);

alter table public.mcp_listing_versions rename column security_score to risk_score;
alter table public.mcp_listing_versions drop constraint if exists mcp_listing_versions_security_score_check;
alter table public.mcp_listing_versions add constraint mcp_listing_versions_risk_score_check
  check (risk_score is null or risk_score between 0 and 100);
update public.mcp_listing_versions set risk_score = null;

alter table public.mcp_listing_versions drop constraint if exists mcp_listing_versions_trust_grade_check;
alter table public.mcp_listing_versions add constraint mcp_listing_versions_trust_grade_check
  check (trust_grade is null or trust_grade in ('A', 'B', 'C', 'D', 'F'));

alter table public.mcp_listing_versions drop column if exists code_score;
alter table public.mcp_listing_versions drop column if exists mcp_score;
alter table public.mcp_listing_versions drop column if exists dependency_score;
