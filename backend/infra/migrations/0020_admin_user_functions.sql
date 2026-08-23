-- Admin panel: read-only views over auth.users that the API cannot reach
-- directly. PostgREST only exposes the `public` schema, so anything needing
-- auth.users has to come through a SECURITY DEFINER function with a pinned
-- search_path.
--
-- Reconstructed from the live database. These were applied out-of-band and
-- never written down, which is the same drift that let 0024 ship without its
-- constraint change.

create or replace function public.admin_list_users(
  p_query text default null,
  p_status text default null,
  p_limit integer default 25,
  p_offset integer default 0
)
returns table(
  user_id uuid, email text, tier text, effective_tier text, status text,
  flagged boolean, paid_until timestamptz, created_at timestamptz,
  last_scan_at timestamptz, scans_this_period bigint, total_count bigint
)
language sql
security definer
set search_path to 'public', 'auth'
as $function$
  with filtered as (
    select
      a.user_id,
      u.email::text as email,
      a.tier,
      -- Mirrors quota.effective_tier(): a paid tier only counts while
      -- paid_until is in the future, since billing is one cycle at a time
      -- with no webhook to downgrade the stored tier on expiry.
      case
        when a.tier = 'free' then 'free'
        when a.paid_until is null then 'free'
        when a.paid_until < now() then 'free'
        else a.tier
      end as effective_tier,
      a.status,
      a.flagged,
      a.paid_until,
      u.created_at,
      (select max(s.created_at) from public.scans s where s.user_id = a.user_id) as last_scan_at,
      (select count(*) from public.scans s
         where s.user_id = a.user_id
           and s.created_at >= date_trunc('month', now())) as scans_this_period
    from public.accounts a
    join auth.users u on u.id = a.user_id
    where (p_query is null or u.email ilike '%' || p_query || '%')
      and (p_status is null or a.status = p_status)
  )
  select
    f.*,
    (select count(*) from filtered) as total_count
  from filtered f
  order by f.created_at desc
  limit p_limit offset p_offset;
$function$;

create or replace function public.admin_user_identity(p_user_id uuid)
returns table(
  user_id uuid, email text, created_at timestamptz, last_sign_in_at timestamptz,
  has_password boolean, providers text[]
)
language sql
security definer
set search_path to 'public', 'auth'
as $function$
  select
    u.id,
    u.email::text,
    u.created_at,
    u.last_sign_in_at,
    -- An OAuth-only account has no password to reset. Supabase still writes
    -- a placeholder for some flows, so presence is tested rather than
    -- assumed from the provider list alone.
    (u.encrypted_password is not null and length(u.encrypted_password) > 0),
    coalesce(
      array(select distinct i.provider::text from auth.identities i where i.user_id = u.id),
      array[]::text[]
    )
  from auth.users u
  where u.id = p_user_id;
$function$;
