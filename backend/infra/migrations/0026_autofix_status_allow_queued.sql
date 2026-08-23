-- 0024 introduced the queued -> in_progress -> fixed/failed lifecycle for
-- whole-scan Fix It runs but left this constraint on the original four
-- values. Every fix request has been failing on the very first write since:
-- PostgREST returns 23514, the API maps it to a generic 502, and the user
-- sees "Upstream data store error" with no indication that the queue state
-- is the problem.
--
-- Cancellation is deliberately not a status here. Cancelling releases a
-- queued finding back to 'none' rather than marking it cancelled, because a
-- finding that was never attempted is genuinely in the same state as one
-- nobody asked to fix, and a terminal-looking 'cancelled' would wrongly
-- suggest it had been tried.
alter table public.findings drop constraint if exists findings_autofix_status_check;

alter table public.findings add constraint findings_autofix_status_check
  check (autofix_status in ('none', 'queued', 'in_progress', 'fixed', 'failed'));
