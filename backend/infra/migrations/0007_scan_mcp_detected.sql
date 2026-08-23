-- Surfaces "does this target actually look like an MCP server?" on scan
-- results. Best-effort: null for target types where the question doesn't
-- apply (a live server URL or pasted mcp.json is MCP by construction);
-- false means the findings are still real, but they're generic code-
-- security findings, not an MCP-specific risk assessment. Confirmed live:
-- scanning a repo with zero MCP relation (pallets/flask) previously
-- produced a fully scored report with MCP-labeled OWASP categories and no
-- indication anywhere that this wasn't an MCP server.
alter table public.scans add column if not exists mcp_detected boolean;
