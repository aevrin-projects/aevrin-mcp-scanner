-- Deleting an account, completely.
--
-- Every table that references auth.users does so ON DELETE CASCADE, so one
-- delete removes the login, the account, scans, findings, API keys, agent
-- snapshots, policies, payments and the rest. This function exists because
-- PostgREST only exposes `public`; auth.users is unreachable from the API
-- without a SECURITY DEFINER hop.
--
-- admin_audit_log deliberately has no foreign key to auth.users, so the
-- record of who deleted whom survives the deletion. An audit trail that
-- disappears with its subject is not an audit trail.

create or replace function public.admin_delete_user(p_user_id uuid)
returns table(email text, scans_deleted bigint, findings_deleted bigint, payments_deleted bigint)
language plpgsql
security definer
set search_path to 'public', 'auth'
as $function$
declare
  v_email text;
  v_scans bigint;
  v_findings bigint;
  v_payments bigint;
begin
  select u.email::text into v_email from auth.users u where u.id = p_user_id;
  if v_email is null then
    raise exception 'no such user';
  end if;

  -- Counted before the delete so the audit entry can say what was destroyed.
  -- Afterwards there is nothing left to count.
  select count(*) into v_scans    from public.scans    where user_id = p_user_id;
  select count(*) into v_findings from public.findings where user_id = p_user_id;
  select count(*) into v_payments from public.payments where user_id = p_user_id;

  delete from auth.users where id = p_user_id;

  return query select v_email, v_scans, v_findings, v_payments;
end;
$function$;

revoke all on function public.admin_delete_user(uuid) from public, anon, authenticated;

comment on function public.admin_delete_user is
  'Deletes a user and every row that cascades from them. Service role only; the API gates it behind an admin session and a fresh TOTP code.';
