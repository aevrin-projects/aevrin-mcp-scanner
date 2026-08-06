-- Two things that make Fix It legible after the fact.
--
-- 1. `scan_diff` answers "did my fix actually work?" by comparing a scan
--    against the previous scan of the same target. Without it, a rescan that
--    still shows findings looks like the fix failed, even when the findings
--    are different ones that were always there.
--
-- 2. `scans.autofix_cancel_requested_at` lets a whole-scan Fix It run be
--    stopped mid-flight. The worker checks it between findings, so the fix
--    already in progress finishes rather than leaving a half-written branch.
--
-- Reconstructed from the live database; applied out-of-band originally.
-- NOTE: the original application of this migration introduced the 'queued'
-- autofix status without extending findings_autofix_status_check, which
-- broke every Fix It request in production. See 0026.

alter table public.scans add column if not exists autofix_cancel_requested_at timestamptz;

comment on column public.scans.autofix_cancel_requested_at is
  'Set when a whole-scan Fix It run is cancelled. The worker checks this between findings; the fix in flight is allowed to finish.';

create or replace function public.scan_diff(p_scan_id uuid, p_user_id uuid)
returns jsonb
language sql
security definer
set search_path to 'public'
as $function$
  with this_scan as (
    select * from public.scans where id = p_scan_id and user_id = p_user_id
  ),
  previous as (
    select s.id
    from public.scans s, this_scan t
    where s.user_id = p_user_id
      and s.target = t.target
      and s.created_at < t.created_at
      and s.status in ('completed', 'incomplete')
    order by s.created_at desc
    limit 1
  ),
  -- Only findings that actually count: a not_tested placeholder or an
  -- excluded fixture path is not something a fix could resolve.
  cur as (
    select distinct f.title, f.file_path, f.tool
    from public.findings f, this_scan t
    where f.scan_id = t.id and f.not_tested = false and f.excluded_path = false
  ),
  prev as (
    select distinct f.title, f.file_path, f.tool
    from public.findings f, previous p
    where f.scan_id = p.id and f.not_tested = false and f.excluded_path = false
  )
  select jsonb_build_object(
    'previous_scan_id', (select id from previous),
    'resolved', coalesce((
      select jsonb_agg(jsonb_build_object('title', title, 'file_path', file_path, 'tool', tool))
      from (select * from prev except select * from cur) r
    ), '[]'::jsonb),
    'introduced', coalesce((
      select jsonb_agg(jsonb_build_object('title', title, 'file_path', file_path, 'tool', tool))
      from (select * from cur except select * from prev) n
    ), '[]'::jsonb),
    'unchanged_count', (select count(*) from (select * from cur intersect select * from prev) u)
  );
$function$;
