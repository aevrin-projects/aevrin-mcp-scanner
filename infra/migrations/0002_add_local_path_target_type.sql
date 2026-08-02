-- CLI `aevrin scan <local-path>` needs a target_type distinct from
-- github_repo/live_mcp_server/config_paste — the website's Screen 1 never
-- exposes this mode (only the CLI runs on the user's own machine), but
-- --upload needs somewhere valid to tag the result.

alter table public.scans drop constraint scans_target_type_check;
alter table public.scans add constraint scans_target_type_check
  check (target_type in ('github_repo', 'live_mcp_server', 'config_paste', 'local_path'));
