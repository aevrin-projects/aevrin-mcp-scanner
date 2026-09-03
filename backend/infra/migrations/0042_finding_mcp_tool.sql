-- analysis.capability_map.attribute_findings_to_tools joins a behavior
-- finding's sink (from adapters/mcp_behavior.py) to the specific declared
-- MCP tool whose function body contains it, using an exact AST-derived
-- range - never the tool's declaration span alone, which ends at the
-- docstring, before a real sink. See that module's own docstring for why.

alter table public.findings
  add column if not exists mcp_tool text;

comment on column public.findings.mcp_tool is
  'Which declared MCP tool this finding''s sink was found inside (analysis.capability_map). Null when the finding is not tool-shaped, or is but no known tool''s body could be shown to contain it - never a guess at the nearest one.';
