-- Let the API read member emails.
--
-- org_member_emails guarded itself with "is the caller a member of this org",
-- written as a test against auth.uid(). The API calls it with the service
-- role, where auth.uid() is null, so the test could never pass and the
-- function returned nothing at all: the Members table showed every person as
-- "Unknown address", including the owner looking at their own workspace.
--
-- The guard is still worth having. `authenticated` holds execute on this
-- function, so without it any signed-in account could call it through
-- PostgREST with someone else's org id and read that workspace's addresses.
-- What it needed was to recognise the one caller that has already done its
-- own authorisation.

create or replace function public.org_member_emails(p_org uuid)
returns table (user_id uuid, email text)
language sql
stable
security definer
set search_path = public, auth, pg_temp
as $$
  select m.user_id, u.email::text
  from public.organization_members m
  join auth.users u on u.id = m.user_id
  where m.org_id = p_org
    and (
      -- The API, which has already required membership before asking.
      (select auth.role()) = 'service_role'
      -- Anyone else: only their own workspace.
      or exists (
        select 1 from public.organization_members me
        where me.org_id = p_org and me.user_id = (select auth.uid())
      )
    );
$$;

revoke all on function public.org_member_emails(uuid) from public, anon;
grant execute on function public.org_member_emails(uuid) to authenticated, service_role;
