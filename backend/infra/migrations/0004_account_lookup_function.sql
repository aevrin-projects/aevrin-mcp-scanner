-- Lets the API answer "does this email already have an account, and does it
-- have a password?" without exposing auth.users directly. Needed because
-- Supabase auto-links identities across providers for the same email, a
-- user who signed up with Google and later tries email/password signup or
-- sign-in needs a precise "you signed in with Google" message instead of a
-- generic error, and that requires reading auth.identities/auth.users,
-- which are never exposed via the Data API.
--
-- SECURITY DEFINER functions in the public schema are callable by anon and
-- authenticated by default (Postgres grants EXECUTE to PUBLIC). This one
-- reads another user's identity/password state by email, so it is
-- explicitly locked to service_role only; never call it from the browser.
create or replace function public.lookup_account_by_email(p_email text)
returns jsonb
language plpgsql
security definer
set search_path = auth, pg_temp
as $$
declare
  v_user auth.users%rowtype;
  v_providers jsonb;
begin
  select * into v_user from auth.users where lower(email) = lower(p_email) limit 1;
  if not found then
    return jsonb_build_object('exists', false, 'providers', '[]'::jsonb, 'has_password', false);
  end if;

  select coalesce(jsonb_agg(distinct provider), '[]'::jsonb) into v_providers
  from auth.identities where user_id = v_user.id;

  return jsonb_build_object(
    'exists', true,
    'providers', v_providers,
    'has_password', (v_user.encrypted_password is not null and v_user.encrypted_password != '')
  );
end;
$$;

revoke all on function public.lookup_account_by_email(text) from public;
revoke all on function public.lookup_account_by_email(text) from anon;
revoke all on function public.lookup_account_by_email(text) from authenticated;
grant execute on function public.lookup_account_by_email(text) to service_role;
