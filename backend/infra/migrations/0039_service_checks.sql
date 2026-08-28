-- Availability history for the public status page.
--
-- Until now the status page ran a single live check in the visitor's browser
-- and kept nothing, so it could show what was true at that instant and
-- nothing else. It said so plainly rather than inventing a "99.98% uptime"
-- figure, which was the right call with no data behind it -- this table is
-- what makes that figure real instead of removing the disclaimer.
--
-- One property shapes everything here: **a gap in this table is not
-- evidence of uptime.** The job that writes it calls the API, so an API
-- outage means no row is written at all rather than a row saying "down".
-- Any reader that computed uptime as ok/recorded would therefore report a
-- total outage as a perfect score -- the exact inversion a status page
-- cannot afford. `services/status.py` treats a day with no checks as
-- `no_data`, never as operational, and the page renders it as a distinct
-- neutral bar. Adding a row per failure is not enough on its own; the
-- absence of a row has to carry meaning too.

create table if not exists public.service_checks (
  id uuid primary key default gen_random_uuid(),
  -- Matches the ids the status page renders. Constrained so a typo in a job
  -- cannot quietly create a fifth service nobody displays.
  service text not null check (service in ('api', 'auth', 'web', 'defectdojo')),
  ok boolean not null,
  -- Null on failure: the time spent failing is not a latency measurement,
  -- and averaging it in would make an outage look like a slow day.
  latency_ms int check (latency_ms is null or latency_ms >= 0),
  -- Short, non-sensitive reason ("timeout", "status 502"). Never a response
  -- body: a body can echo request content, and request content is one
  -- careless write away from being a credential.
  detail text,
  checked_at timestamptz not null default now()
);

-- The only read pattern is "this service, newest first, inside a window".
create index if not exists service_checks_service_time_idx
  on public.service_checks (service, checked_at desc);

alter table public.service_checks enable row level security;

-- Genuinely public information: this is what the status page publishes, and
-- it carries no user, org, or scan data. Read-only to everyone; writes go
-- through the API's service-role key, which bypasses RLS, so no insert or
-- update policy is granted to anyone here.
create policy service_checks_public_select on public.service_checks
  for select to authenticated, anon using (true);
