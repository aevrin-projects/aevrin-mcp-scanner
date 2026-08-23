import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { DeviceApproveForm } from "@/views/device";

// The one flow that must resist disposable-email abuse (addendum §3/§4):
// deliberately requires a real session here rather than relying on the
// global proxy redirect gate, since /device is listed as a public path (it
// has to be reachable pre-auth so an unauthenticated visit lands in /login
// with a return path, not a bare 404). The proxy still resolves identity
// for every request regardless of path (see lib/supabase/proxy.ts), so
// reading its header here is exactly as trustworthy as calling Supabase
// again; it just doesn't risk a second, racing refresh-token exchange.
export default async function DevicePage({
  searchParams,
}: {
  searchParams: Promise<{ user_code?: string }>;
}) {
  const { user_code } = await searchParams;
  const headersList = await headers();
  const email = headersList.get("x-aevrin-user-email");

  if (!email) {
    const next = `/device${user_code ? `?user_code=${encodeURIComponent(user_code)}` : ""}`;
    redirect(`/login?next=${encodeURIComponent(next)}`);
  }

  return <DeviceApproveForm initialUserCode={user_code ?? ""} />;
}
