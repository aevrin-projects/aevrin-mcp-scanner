-- LLM triage results (AEVRIN_ACCURACY_PRICING_PROMPT.md §2), paid tiers only.
-- Kept distinct from the existing human triage_status/triage_reason/triaged_at
-- columns (finding_triage_audit migration); these are a second, LLM-authored
-- opinion shown *alongside* the deterministic result, never blended into it
-- (§4: "visibly distinct from each other, don't blend into one number").
alter table public.findings add column if not exists llm_classification text check (llm_classification in ('confirmed', 'likely_false_positive', 'needs_review'));
alter table public.findings add column if not exists llm_severity text check (llm_severity in ('critical', 'high', 'medium', 'low', 'info'));
alter table public.findings add column if not exists llm_reasoning text;
alter table public.findings add column if not exists llm_remediation text;
alter table public.findings add column if not exists llm_model text;
alter table public.findings add column if not exists llm_triaged_at timestamptz;

-- Plain-language, once-per-scan summary (Pro/Team), belongs on scans, not
-- repeated per finding.
alter table public.scans add column if not exists llm_summary text;
