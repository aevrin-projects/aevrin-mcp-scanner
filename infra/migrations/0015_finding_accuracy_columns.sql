-- Section 1 accuracy-layer fields on findings (AEVRIN_ACCURACY_PRICING_PROMPT.md §1).
-- These mirror the new fields scanner-core's Finding model now carries after
-- postprocess_findings() runs (fixture-path exclusion, cross-scanner dedup,
-- root-cause grouping, EPSS, CISA KEV, dependency dev/prod scope).
alter table public.findings add column if not exists excluded_path boolean not null default false;
alter table public.findings add column if not exists confidence text;
alter table public.findings add column if not exists original_severity text check (original_severity in ('critical', 'high', 'medium', 'low', 'info'));
alter table public.findings add column if not exists epss_score real;
alter table public.findings add column if not exists in_kev boolean not null default false;
alter table public.findings add column if not exists dependency_scope text check (dependency_scope in ('production', 'development', 'unknown'));
alter table public.findings add column if not exists corroborated_by text[] not null default '{}';
alter table public.findings add column if not exists occurrence_count integer not null default 1;
alter table public.findings add column if not exists additional_locations jsonb not null default '[]'::jsonb;
