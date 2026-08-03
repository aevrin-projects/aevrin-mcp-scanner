-- The hook's cached decision needs to know whether the last scan behind it
-- was actually reliable — without this, an incomplete scan (see
-- 0008_scan_reliability.sql) with zero findings would read exactly like a
-- clean scan and the hook would silently allow an unverified install.

alter table public.hook_cache add column if not exists last_status text;
