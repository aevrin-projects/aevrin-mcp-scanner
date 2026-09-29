-- Two database functions still read columns 0047 dropped, and five
-- SECURITY DEFINER functions were executable by anyone holding the public
-- anon key.
--
-- SAFE TO APPLY BEFORE OR AFTER THE DEPLOY. No table, column or data change:
-- two functions are replaced with the same signature and result shape, and
-- EXECUTE is narrowed to the API's own role.
--
-- 1. `findings.not_tested` and `findings.excluded_path` were dropped in
--    0047_mcp_engine_replacement.sql, but two functions still filtered on
--    them, so every call failed with 42703 (undefined column):
--      * admin_analytics  -> GET /admin/analytics returned "Upstream data
--                            store error" on every load.
--      * scan_diff        -> the scan page's "since the last scan" diff
--                            failed the same way.
--    0047 already explains why those filters mean nothing now: a finding
--    describes a tool a live server returned, so there is no placeholder row
--    and no fixture path to leave out. Both functions are recreated below
--    with only those filters removed; everything else is the live definition
--    as it stood (read back with pg_get_functiondef before writing this).
--    The earlier bodies were never in this repository (0020-0023 are
--    pointers), which is how 0047 missed them; they are here in full now.
--
-- 2. Postgres grants EXECUTE on a new function to PUBLIC, and Supabase's
--    PostgREST serves every function in `public` to the `anon` and
--    `authenticated` roles. 0004 (lookup_account_by_email) and 0032
--    (admin_delete_user) revoke that; these five never did:
--      admin_list_users, admin_user_identity, admin_account_usage,
--      admin_analytics, scan_diff
--    None checks its caller: they trust that only the API (service_role)
--    calls them, after its own admin or ownership check. Callable over
--    /rest/v1/rpc with the anon key that ships in the frontend, the admin
--    ones return every account's email, plan and usage, and scan_diff takes
--    the user id as an argument. Only the API calls any of them, always as
--    service_role, so revoking the rest changes nothing it does.
--    (is_org_member, my_org and org_member_emails stay callable: RLS policies
--    use the first two, and all three answer only about the caller's own
--    workspace. stamp_org_id and sync_favorite_count are trigger functions,
--    which cannot be called directly.)

create or replace function public.admin_analytics(p_days integer DEFAULT 30)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public', 'auth'
AS $function$
  with span as (select (now() - make_interval(days => p_days)) as since)
  select jsonb_build_object(
    'window_days', p_days,

    -- Growth
    'accounts_total', (select count(*) from public.accounts),
    'signups_in_window', (select count(*) from auth.users, span where created_at >= span.since),
    'signups_by_day', (
      select coalesce(jsonb_agg(jsonb_build_object('day', d, 'count', c) order by d), '[]'::jsonb)
      from (
        select date_trunc('day', u.created_at)::date as d, count(*) as c
        from auth.users u, span where u.created_at >= span.since
        group by 1
      ) t
    ),
    'plan_distribution', (
      select coalesce(jsonb_object_agg(tier, n), '{}'::jsonb)
      from (
        -- Effective tier, not stored: a lapsed paid account is Free in
        -- every way that matters to the product.
        select case
          when a.tier = 'free' then 'free'
          when a.paid_until is null or a.paid_until < now() then 'free'
          else a.tier
        end as tier, count(*) as n
        from public.accounts a group by 1
      ) t
    ),
    'status_distribution', (
      select coalesce(jsonb_object_agg(status, n), '{}'::jsonb)
      from (select status, count(*) as n from public.accounts group by 1) t
    ),

    -- Usage by surface
    'scans_total', (select count(*) from public.scans),
    'scans_in_window', (select count(*) from public.scans, span where created_at >= span.since),
    'scans_by_source', (
      select coalesce(jsonb_object_agg(source, n), '{}'::jsonb)
      from (select source, count(*) as n from public.scans, span where created_at >= span.since group by 1) t
    ),
    'scans_by_day', (
      select coalesce(jsonb_agg(jsonb_build_object('day', d, 'count', c) order by d), '[]'::jsonb)
      from (
        select date_trunc('day', s.created_at)::date as d, count(*) as c
        from public.scans s, span where s.created_at >= span.since group by 1
      ) t
    ),
    'scan_outcomes', (
      select coalesce(jsonb_object_agg(status, n), '{}'::jsonb)
      from (select status, count(*) as n from public.scans, span where created_at >= span.since group by 1) t
    ),
    'avg_findings_per_scan', (
      select round(coalesce(avg(c), 0), 1) from (
        select count(f.id) as c from public.scans s
        left join public.findings f on f.scan_id = s.id
        , span where s.created_at >= span.since group by s.id
      ) t
    ),

    -- CLI and hook adoption. Installs themselves aren't observable from
    -- here (npm/PyPI downloads live with those registries); what we can
    -- honestly measure is authentication and actual use.
    'cli_authenticated_accounts', (select count(distinct user_id) from public.api_keys where revoked_at is null),
    'device_authorizations', (
      select coalesce(jsonb_object_agg(client_kind, n), '{}'::jsonb)
      from (select client_kind, count(*) as n from public.device_codes group by 1) t
    ),
    'cli_active_accounts', (select count(distinct user_id) from public.scans, span where source = 'cli' and created_at >= span.since),
    'hook_active_accounts', (select count(distinct user_id) from public.scans, span where source = 'hook' and created_at >= span.since),
    'hook_cached_targets', (select count(*) from public.hook_cache),
    'hook_overrides_used', (select count(*) from public.hook_overrides),

    -- Auto-fix
    'autofix_prs_opened', (select count(*) from public.findings where autofix_status = 'fixed'),
    'autofix_prs_in_window', (select count(*) from public.findings, span where autofix_status = 'fixed' and autofix_at >= span.since),

    -- Revenue, from the billing provider's own recorded payments
    'payments_paid_count', (select count(*) from public.payments where status = 'paid'),
    'revenue_paise_total', (select coalesce(sum(amount_paise), 0) from public.payments where status = 'paid'),
    'revenue_paise_in_window', (select coalesce(sum(amount_paise), 0) from public.payments, span where status = 'paid' and created_at >= span.since),
    'payments_by_status', (
      select coalesce(jsonb_object_agg(status, n), '{}'::jsonb)
      from (select status, count(*) as n from public.payments group by 1) t
    ),

    -- Anti-abuse review queue
    'flagged_accounts', (select count(*) from public.accounts where flagged),
    'abuse_signal_count', (select count(*) from public.abuse_signals),

    -- Traffic
    'pageviews_in_window', (select count(*) from public.page_views, span where created_at >= span.since),
    'visitors_in_window', (select count(distinct visitor_hash) from public.page_views, span where created_at >= span.since),
    'top_pages', (
      select coalesce(jsonb_agg(jsonb_build_object('path', path, 'views', v, 'visitors', vis) order by v desc), '[]'::jsonb)
      from (
        select path, count(*) as v, count(distinct visitor_hash) as vis
        from public.page_views, span where created_at >= span.since
        group by 1 order by 2 desc limit 15
      ) t
    ),
    'top_referrers', (
      select coalesce(jsonb_agg(jsonb_build_object('referrer', r, 'views', v) order by v desc), '[]'::jsonb)
      from (
        select coalesce(nullif(referrer, ''), 'direct') as r, count(*) as v
        from public.page_views, span where created_at >= span.since
        group by 1 order by 2 desc limit 10
      ) t
    ),
    'views_by_day', (
      select coalesce(jsonb_agg(jsonb_build_object('day', d, 'views', v, 'visitors', vis) order by d), '[]'::jsonb)
      from (
        select date_trunc('day', created_at)::date as d, count(*) as v, count(distinct visitor_hash) as vis
        from public.page_views, span where created_at >= span.since group by 1
      ) t
    ),
    'devices', (
      select coalesce(jsonb_object_agg(coalesce(device, 'unknown'), n), '{}'::jsonb)
      from (select device, count(*) as n from public.page_views, span where created_at >= span.since group by 1) t
    ),
    'countries', (
      select coalesce(jsonb_agg(jsonb_build_object('country', c, 'views', v) order by v desc), '[]'::jsonb)
      from (
        select coalesce(country, 'unknown') as c, count(*) as v
        from public.page_views, span where created_at >= span.since group by 1 order by 2 desc limit 12
      ) t
    )
  );
$function$;

create or replace function public.scan_diff(p_scan_id uuid, p_user_id uuid)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  with this_scan as (
    select * from public.scans where id = p_scan_id and user_id = p_user_id
  ),
  previous as (
    select s.id
    from public.scans s, this_scan t
    where s.user_id = p_user_id
      and s.target = t.target
      and s.created_at < t.created_at
      and s.status in ('completed', 'incomplete')
    order by s.created_at desc
    limit 1
  ),
  cur as (
    select distinct f.title, f.file_path, f.tool
    from public.findings f, this_scan t
    where f.scan_id = t.id
  ),
  prev as (
    select distinct f.title, f.file_path, f.tool
    from public.findings f, previous p
    where f.scan_id = p.id
  )
  select jsonb_build_object(
    'previous_scan_id', (select id from previous),
    'resolved', coalesce((
      select jsonb_agg(jsonb_build_object('title', title, 'file_path', file_path, 'tool', tool))
      from (select * from prev except select * from cur) r
    ), '[]'::jsonb),
    'introduced', coalesce((
      select jsonb_agg(jsonb_build_object('title', title, 'file_path', file_path, 'tool', tool))
      from (select * from cur except select * from prev) n
    ), '[]'::jsonb),
    'unchanged_count', (select count(*) from (select * from cur intersect select * from prev) u)
  );
$function$;

revoke all on function public.admin_list_users(text, text, integer, integer) from public, anon, authenticated;
revoke all on function public.admin_user_identity(uuid) from public, anon, authenticated;
revoke all on function public.admin_account_usage() from public, anon, authenticated;
revoke all on function public.admin_analytics(integer) from public, anon, authenticated;
revoke all on function public.scan_diff(uuid, uuid) from public, anon, authenticated;

grant execute on function public.admin_list_users(text, text, integer, integer) to service_role;
grant execute on function public.admin_user_identity(uuid) to service_role;
grant execute on function public.admin_account_usage() to service_role;
grant execute on function public.admin_analytics(integer) to service_role;
grant execute on function public.scan_diff(uuid, uuid) to service_role;
