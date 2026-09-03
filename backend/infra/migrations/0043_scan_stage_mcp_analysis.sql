-- StageName.MCP_ANALYSIS (Aevrin's own behavior rule pack, adapters/
-- mcp_behavior.py, joined to a declared tool via analysis/capability_map.py)
-- is now a real stage run_pipeline invokes, between DEPENDENCIES and
-- TOOL_DESCRIPTION_CHECK. Widen the name check the same way 0001_init.sql
-- originally declared it, rather than dropping the constraint entirely.

alter table public.scan_stages drop constraint if exists scan_stages_name_check;
alter table public.scan_stages add constraint scan_stages_name_check
  check (
    name in (
      'cloning', 'static_analysis', 'secrets', 'dependencies',
      'mcp_analysis', 'tool_description_check', 'aggregating'
    )
  );
