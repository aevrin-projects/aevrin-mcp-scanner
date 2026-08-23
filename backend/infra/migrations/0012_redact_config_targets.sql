-- Pasted MCP configuration can contain environment values or credentials.
-- The scan worker needs the submitted JSON only for the lifetime of the job;
-- durable scan history should retain a non-reversible label, not the payload.

delete from public.rug_pull_signatures as signature
using public.scans as scan
where scan.target_type = 'config_paste'
  and signature.user_id = scan.user_id
  and signature.target = scan.target;

delete from public.hook_cache as cache
using public.scans as scan
where scan.target_type = 'config_paste'
  and cache.user_id = scan.user_id
  and cache.target = scan.target;

delete from public.hook_overrides as hook_override
using public.scans as scan
where scan.target_type = 'config_paste'
  and hook_override.user_id = scan.user_id
  and hook_override.target = scan.target;

update public.scans
set target = 'Pasted MCP configuration · historical-redaction'
where target_type = 'config_paste';
