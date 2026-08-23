-- When a Fix It pull request was actually opened.
--
-- The auto_fix usage counter lived only in Redis, and unlike the scan buckets
-- it had no durable fallback (those are recounted from `scans`). Confirmed
-- live: a PR was opened successfully, the counter increment hit an exhausted
-- Upstash quota, and the usage meter stayed at zero with the PR real and
-- open. This column makes the count recoverable from Postgres.

alter table public.findings
  add column if not exists autofix_at timestamptz;

comment on column public.findings.autofix_at is
  'When Fix It opened a pull request for this finding. Durable source for the auto_fix usage counter when Redis is unavailable.';

update public.findings f
set autofix_at = coalesce(s.completed_at, s.created_at)
from public.scans s
where s.id = f.scan_id
  and f.autofix_status = 'fixed'
  and f.autofix_pr_url is not null
  and f.autofix_at is null;

create index if not exists findings_autofix_at_idx
  on public.findings (user_id, autofix_at)
  where autofix_status = 'fixed';
