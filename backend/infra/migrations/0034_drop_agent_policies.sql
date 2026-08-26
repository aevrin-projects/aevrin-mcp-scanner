-- Remove the agent policies feature.
--
-- Four switches that labelled a server or agent as blocked / approval
-- required, plus an audit trail of who changed them. They never enforced
-- anything -- Aevrin has no channel to a user's machines -- so what they
-- produced was a second opinion sitting next to the trust grade that already
-- said the same thing. Role-based access in a workspace is where permission
-- decisions belong now.
--
-- The audit rows go with them. They record only which switch was flipped and
-- by whom, never a secret or an environment value, and there is nothing left
-- that can read them.

drop table if exists public.agent_policy_audit;
drop table if exists public.agent_policies;
