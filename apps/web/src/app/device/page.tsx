import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { DeviceApproveForm } from "./device-approve-form";

// The one flow that must resist disposable-email abuse (addendum §3/§4) —
// deliberately requires a real session here rather than relying on the
// global proxy gate, since /device is listed as a public path (it has to be
// reachable pre-auth so an unauthenticated visit lands in /login with a
// return path, not a bare 404).
export default async function DevicePage({
  searchParams,
}: {
  searchParams: Promise<{ user_code?: string }>;
}) {
  const { user_code } = await searchParams;
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  const claims = data?.claims;

  if (!claims) {
    const next = `/device${user_code ? `?user_code=${encodeURIComponent(user_code)}` : ""}`;
    redirect(`/login?next=${encodeURIComponent(next)}`);
  }

  return <DeviceApproveForm initialUserCode={user_code ?? ""} />;
}
