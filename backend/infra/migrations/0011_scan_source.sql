-- Record which authenticated product surface created each durable scan so
-- CLI uploads remain distinguishable from dashboard jobs in shared history.

alter table public.scans
  add column if not exists source text not null default 'dashboard';

update public.scans
set source = 'cli'
where target_type = 'local_path'
  and source = 'dashboard';

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'scans_source_check'
      and conrelid = 'public.scans'::regclass
  ) then
    alter table public.scans
      add constraint scans_source_check
      check (source in ('dashboard', 'cli', 'hook'));
  end if;
end $$;

comment on column public.scans.source is
  'Authenticated product surface that created the scan: dashboard, cli, or hook.';
