-- Which step of a fix is running right now.
--
-- The progress dialog previously showed one static sentence per finding
-- ("Drafting patch, re-running the scanner, opening a PR") for the entire
-- run, which is three steps described at once and no indication of which is
-- actually happening. These stages are written by the worker as it goes, so
-- the dialog reports real state rather than a caption.
alter table public.findings add column if not exists autofix_stage text;

alter table public.findings drop constraint if exists findings_autofix_stage_check;
alter table public.findings add constraint findings_autofix_stage_check
  check (autofix_stage is null or autofix_stage in (
    'analysing',   -- reading the finding and its surrounding code
    'generating',  -- drafting the patch
    'verifying',   -- re-running the originating scanner against the patch
    'authorizing', -- checking repository access
    'opening_pr'   -- creating the branch, commit, and pull request
  ));

comment on column public.findings.autofix_stage is
  'Current step of an in-flight Fix It run. Null once the run reaches a terminal autofix_status.';
