-- Component detection (aevrin_scanner_core.analysis.mcp_detection.McpComponent)
-- identifies which specific directories inside a repository independently
-- look like a self-contained MCP server, so a monorepo's unrelated
-- frontend/backend do not get reported as part of the MCP surface, and the
-- real component can be named by its own directory. See the docstring on
-- McpComponent and on Scan.mcp_components for why this is additive
-- evidence, never a replacement for the existing whole-repository
-- mcp_detected/mcp_detection_confidence verdict.

alter table public.scans
  add column if not exists mcp_components jsonb not null default '[]'::jsonb;

comment on column public.scans.mcp_components is
  'Directories independently detected as their own MCP server: [{"root", "confidence", "evidence"}]. Empty for a single-package repo with no manifest-owning subdirectory of its own, for a repo with no such directory, and for target types with no repository to partition (live_mcp_server, config_paste).';
