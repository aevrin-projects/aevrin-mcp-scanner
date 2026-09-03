-- scanner-core's capability_summary() (analysis/mcp_detection.py) has
-- always been computable from a scan's discovered tools - it existed with
-- its own unit test (test_capability_summary_feeds_the_trust_grade) but no
-- caller ever invoked it. Scan.mcp_capabilities (pipeline/orchestrator.py)
-- now carries its result; this is what lets the marketplace grade finally
-- read real declared-capability evidence (services/marketplace/scanning.py)
-- instead of always passing capabilities=None. See DECISIONS.md ADR-020.

alter table public.scans
  add column if not exists mcp_capabilities jsonb;

comment on column public.scans.mcp_capabilities is
  'analysis.mcp_detection.capability_summary() over this scan''s declared tools: {can_execute, can_write, can_read, handles_credentials, makes_network_calls}, all bool. Null (not a dict of all-false) when tool discovery never ran for this target - a live server URL, a pasted config, or a repository that isn''t an MCP server - since an unestablished capability must stay distinguishable from a confirmed absence of one.';
