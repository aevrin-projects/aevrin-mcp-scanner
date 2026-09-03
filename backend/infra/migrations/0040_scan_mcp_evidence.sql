-- The scan pipeline (backend/scanner-core/aevrin_scanner_core/pipeline/
-- orchestrator.py) has always computed scan.mcp_detection_confidence,
-- scan.mcp_detection_evidence and scan.mcp_tools_declared - they exist on
-- the Scan model, are set on every run, and are what MCP_SCANNING.md
-- describes as being "shown in the report". None of the three ever reached
-- a column: _persist_completed_scan only ever wrote status/score/
-- mcp_detected/unreliable_stages/completed_at, so the value was computed
-- and then discarded on every single scan. This closes that gap.

alter table public.scans
  add column if not exists mcp_detection_confidence text,
  add column if not exists mcp_detection_evidence text[] not null default '{}',
  add column if not exists mcp_tools_declared text[] not null default '{}';

comment on column public.scans.mcp_detection_confidence is
  'How confidently mcp_detected was established: high | medium | low | none. Null for target types where MCP-ness is by construction (live_mcp_server, config_paste).';
comment on column public.scans.mcp_detection_evidence is
  'Short human-readable evidence lines behind mcp_detection_confidence, e.g. "sdk_dependency: depends on fastmcp".';
comment on column public.scans.mcp_tools_declared is
  'Tool names read out of the repository''s own registration sites (discover_tools()). Empty means none found, not "nothing exposed" - see the pipeline docstring on why those read differently.';
