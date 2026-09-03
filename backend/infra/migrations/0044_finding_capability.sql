-- The normalized capability a finding is about (adapters/mcp_behavior.py's
-- fixed vocabulary: shell_execution, credential_access, etc). Was only ever
-- readable from `findings.raw` (adapter debug output, not a contract);
-- analysis.declared_vs_observed needs it as real, typed data.

alter table public.findings
  add column if not exists capability text;

comment on column public.findings.capability is
  'The normalized capability vocabulary term this finding is about (adapters/mcp_behavior.py). Null for every tool except the MCP behavior pack.';
