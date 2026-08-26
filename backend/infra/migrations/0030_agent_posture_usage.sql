-- Agent posture scans are metered like every other scan, on the same buckets,
-- the same rolling anchor and the same tier_limits row. One `aevrin agent
-- scan --upload` is one unit regardless of how many agents it found: Claude
-- Code and Codex discovered by the same command are one posture scan, not two.
--
-- monitored_devices is the fleet size a plan covers. It is a count of
-- machines, not of agents, because a machine is the thing someone adds.
-- NULL means unlimited, the convention every other column here already uses.

alter table public.tier_limits
  add column if not exists agent_scans_per_month integer,
  add column if not exists monitored_devices integer;

-- Proportionate to the existing CLI allowance rather than a new pricing idea:
-- posture discovery costs Aevrin nothing to run (no scanner, no container),
-- so the limit exists to bound fleet size, not compute.
update public.tier_limits set agent_scans_per_month = 10,  monitored_devices = 1    where tier = 'free';
update public.tier_limits set agent_scans_per_month = 100, monitored_devices = 3    where tier = 'hobby';
update public.tier_limits set agent_scans_per_month = 400, monitored_devices = 10   where tier = 'pro';
update public.tier_limits set agent_scans_per_month = null, monitored_devices = null where tier = 'team';

comment on column public.tier_limits.agent_scans_per_month is
  'Agent posture scans per rolling month. One `aevrin agent scan --upload` is one, however many agents it reports.';
comment on column public.tier_limits.monitored_devices is
  'Machines whose posture this plan tracks. NULL means unlimited.';
