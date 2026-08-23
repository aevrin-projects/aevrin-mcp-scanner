-- Make false-positive reports auditable. The status already existed, but a
-- bare status cannot explain why a result was suppressed from risk summaries.

alter table public.findings add column if not exists triage_reason text;
alter table public.findings add column if not exists triaged_at timestamptz;

-- Preserve reports created before reasons were required so the new
-- constraint can be installed without discarding historical state.
update public.findings
set
  triage_reason = 'Marked as a false positive before triage reasons were required.',
  triaged_at = coalesce(triaged_at, created_at)
where triage_status = 'false_positive'
  and (triage_reason is null or btrim(triage_reason) = '');

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'findings_false_positive_reason_check'
      and conrelid = 'public.findings'::regclass
  ) then
    alter table public.findings
      add constraint findings_false_positive_reason_check
      check (
        triage_status <> 'false_positive'
        or (
          triage_reason is not null
          and char_length(btrim(triage_reason)) between 3 and 1000
        )
      );
  end if;
end $$;
