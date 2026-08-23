-- Adds the "incomplete scan" integrity signal: previously, when every tool
-- in a category (static analysis, secrets, dependencies) failed to execute
-- (Docker not running, a missing binary, no network), the scan still
-- reported a clean 100/100 result, because an empty findings list is
-- indistinguishable from "nothing found" unless tracked explicitly.

alter table public.scans drop constraint scans_status_check;
alter table public.scans add constraint scans_status_check
  check (status in ('queued', 'running', 'completed', 'failed', 'incomplete'));

alter table public.scans add column if not exists unreliable_stages text[] not null default '{}';
