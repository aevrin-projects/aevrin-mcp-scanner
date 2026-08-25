-- Agent posture: the current state of each AI coding agent on each device.
--
-- One row per (user, device, agent). A snapshot describes what is true on a
-- machine right now, and the dashboard's question is "what am I running" --
-- so a re-scan replaces the previous answer instead of appending to a log.
-- Change history is a separate feature and is deliberately not built here;
-- an empty history table would only look like one that works.
--
-- The whole normalised snapshot is stored as jsonb rather than exploded into
-- tables for MCP servers, skills, hooks and permissions. The shape is already
-- versioned by schema_version and is written and read as one document; five
-- child tables would buy join-shaped queries nothing here asks for.
--
-- Credential VALUES are never present in this document. The discovery model
-- has no field for one, and the API rejects a payload that tries.

create table if not exists public.agent_snapshots (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  -- SHA-256 of the OS machine id, as already sent at device login. Falls
  -- back to a hash of the hostname when the platform id is unreadable.
  device_id text not null,
  hostname text not null,
  agent_type text not null check (agent_type in ('claude_code', 'codex', 'cursor', 'gemini_cli')),
  schema_version text not null,
  snapshot jsonb not null,
  reported_at timestamptz not null default now(),
  unique (user_id, device_id, agent_type)
);

comment on table public.agent_snapshots is
  'Latest normalised posture snapshot per user, device and agent. Never contains credential values.';

alter table public.agent_snapshots enable row level security;

-- Reads only. Every write goes through the API's service-role path, which is
-- what validates the payload before it is stored.
create policy agent_snapshots_owner_select on public.agent_snapshots for select to authenticated
  using (user_id = (select auth.uid()));
create policy agent_snapshots_owner_delete on public.agent_snapshots for delete to authenticated
  using (user_id = (select auth.uid()));
