"use client";

import { usePathname, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { AuthenticatedAppShell } from "@/components/authenticated-app-shell";
import { PublicNavbar } from "@/components/public-navbar";

const APP_ROUTE_PREFIXES = ["/dashboard", "/scans", "/settings", "/integrations"];

export function LayoutChrome({
  children,
  email,
}: {
  children: React.ReactNode;
  email?: string | null;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const isAppRoute = APP_ROUTE_PREFIXES.some((prefix) => pathname.startsWith(prefix));

  async function signOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  if (email && isAppRoute) {
    return (
      <AuthenticatedAppShell email={email} onSignOut={signOut}>
        {children}
      </AuthenticatedAppShell>
    );
  }

  return (
    <>
      <PublicNavbar signedIn={Boolean(email)} />
      <main className="flex-1">{children}</main>
    </>
  );
}
