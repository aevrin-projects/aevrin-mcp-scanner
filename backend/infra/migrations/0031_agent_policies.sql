-- Policies, as structured data rather than a language.
--
-- Four booleans on one row per account. Nobody should have to write YAML to
-- block a dangerous MCP server, and a policy DSL is a parser, an evaluator, a
-- validator and an error-message surface for a product that today needs four
-- switches.
--
-- Every policy is OFF by default. A grade is a recommendation until someone
-- decides it should be enforcement, and Aevrin turning that on unasked would
-- be making a security decision on a user's behalf.

create table if not exists public.agent_policies (
  user_id uuid primary key references auth.users (id) on delete cascade,
  -- A server its own scan graded D.
  block_grade_d boolean not null default false,
  -- A server graded C: usable, worth a human deciding each time.
  require_approval_grade_c boolean not null default false,
  -- An agent that runs commands with nothing put to a human first.
  block_unattended_shell boolean not null default false,
  -- An agent that can reach anything on the network.
  block_unrestricted_network boolean not null default false,
  updated_at timestamptz not null default now()
);

alter table public.agent_policies enable row level security;

create policy agent_policies_owner_all on public.agent_policies for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- What changed, who changed it, and what it was before. Not a general event
-- stream: only actions that actually exist get rows, so an empty table means
-- nothing happened rather than that the feature was never wired up.
create table if not exists public.agent_policy_audit (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  actor text not null,
  action text not null,
  before jsonb,
  after jsonb,
  request_id text,
  created_at timestamptz not null default now()
);

create index if not exists agent_policy_audit_user_created_idx
  on public.agent_policy_audit (user_id, created_at desc);

alter table public.agent_policy_audit enable row level security;

-- Read-only to the owner. Writes go through the API's service role, which is
-- what makes the record something the actor cannot quietly edit afterwards.
create policy agent_policy_audit_owner_select on public.agent_policy_audit for select to authenticated
  using (user_id = (select auth.uid()));

comment on table public.agent_policy_audit is
  'Policy changes only. Never contains secrets or environment values.';
