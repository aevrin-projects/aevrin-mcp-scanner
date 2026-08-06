-- Per-account usage for the admin analytics page: every quota bucket for
-- every account, with the limit actually in force (override, or plan default
-- plus any purchased auto-fix bonus) rather than the plan default alone.
--
-- Reconstructed from the live database; applied out-of-band originally.

create or replace function public.admin_account_usage()
returns table(
  user_id uuid, email text, tier text, effective_tier text, status text,
  period_start timestamptz, bucket text, used bigint, limit_value integer,
  is_override boolean, pct numeric
)
language sql
security definer
set search_path to 'public', 'auth'
as $function$
  with acct as (
    select
      a.user_id,
      u.email::text as email,
      a.tier,
      case
        when a.tier = 'free' then 'free'
        when a.paid_until is null or a.paid_until < now() then 'free'
        else a.tier
      end as effective_tier,
      a.status,
      a.auto_fix_bonus_prs,
      -- Rolling monthly anchor from signup day, same as quota._period_start.
      (date_trunc('day', now())
        - make_interval(days =>
            case when extract(day from now())::int >= a.signup_anchor_day
                 then extract(day from now())::int - a.signup_anchor_day
                 else extract(day from now())::int + 30 - a.signup_anchor_day
            end)) as period_start
    from public.accounts a
    join auth.users u on u.id = a.user_id
  ),
  buckets as (select unnest(array['cli','hook','dashboard','auto_fix']) as bucket),
  resolved as (
    select
      c.*,
      b.bucket,
      -- Override first, then the plan default.
      o.limit_value as override_value,
      (o.user_id is not null) as has_override,
      case b.bucket
        when 'cli' then tl.cli_scans_per_month
        when 'hook' then tl.hook_scans_per_month
        when 'dashboard' then tl.dashboard_scans_per_month
        else tl.auto_fix_prs_per_month
      end as plan_limit
    from acct c
    cross join buckets b
    join public.tier_limits tl on tl.tier = c.effective_tier
    left join public.account_quota_overrides o
      on o.user_id = c.user_id
     and o.bucket = b.bucket
     and (o.expires_at is null or o.expires_at > now())
  ),
  counted as (
    select
      r.*,
      case
        when r.bucket = 'auto_fix' then (
          select count(*) from public.findings f
          where f.user_id = r.user_id and f.autofix_status = 'fixed' and f.autofix_at >= r.period_start
        )
        else (
          select count(*) from public.scans s
          where s.user_id = r.user_id and s.source = r.bucket and s.created_at >= r.period_start
        )
      end as used
    from resolved r
  )
  select
    c.user_id,
    c.email,
    c.tier,
    c.effective_tier,
    c.status,
    c.period_start,
    c.bucket,
    c.used,
    -- auto_fix alone stacks a purchased/comped bonus on the tier allowance.
    case
      when c.has_override then c.override_value
      when c.bucket = 'auto_fix' and c.plan_limit is not null
        then c.plan_limit + coalesce(c.auto_fix_bonus_prs, 0)
      else c.plan_limit
    end as limit_value,
    c.has_override,
    case
      when (case when c.has_override then c.override_value else c.plan_limit end) is null then null
      when (case when c.has_override then c.override_value else c.plan_limit end) = 0 then null
      else round(100.0 * c.used /
        (case when c.has_override then c.override_value
              when c.bucket = 'auto_fix' then c.plan_limit + coalesce(c.auto_fix_bonus_prs, 0)
              else c.plan_limit end), 0)
    end as pct
  from counted c
  order by c.email, c.bucket;
$function$;
