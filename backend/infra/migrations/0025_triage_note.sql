-- A scan whose AI review was capped must say so. Without this the report
-- looks fully reviewed and a user reasonably assumes every finding got a
-- second opinion, which on a large repo is not true.
alter table public.scans add column if not exists triage_note text;

comment on column public.scans.triage_note is
  'User-facing sentence set when LLM triage covered only part of the findings (per-scan cap). Null means triage was either complete or did not run.';
