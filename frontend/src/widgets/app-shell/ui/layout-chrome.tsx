"use client";

import { usePathname, useRouter } from "next/navigation";
import { createClient } from "@/shared/lib/supabase/client";
import { AuthenticatedAppShell } from "@/widgets/app-shell";
import { PublicNavbar } from "@/widgets/public-navbar";

// `/marketplace` is here even though it is publicly browsable, and the
// distinction is handled below rather than by the list: a signed-in visitor
// gets the sidebar, a signed-out one gets the marketing navbar, because the
// guard is `email && isAppRoute`. That is the right split for a catalogue
// that has to be readable without an account and navigable with one.
const APP_ROUTE_PREFIXES = [
  "/dashboard",
  "/scans",
  "/settings",
  "/integrations",
  "/usage",
  "/agents",
  "/marketplace",
];

// Onboarding is a focused, single-decision flow: it carries its own logo,
// progress indicator, and Skip control, so the marketing navbar on top of it
// produced a double header and offered escape routes that drop people out of
// setup mid-way.
// Routes that own the whole viewport and supply their own branding, the
// site header would only add a band of chrome above a full-bleed layout.
const BARE_ROUTE_PREFIXES = ["/onboarding", "/login", "/admin"];

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
  const isBareRoute = BARE_ROUTE_PREFIXES.some((prefix) => pathname.startsWith(prefix));

  async function signOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  if (isBareRoute) {
    return <main className="flex-1">{children}</main>;
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
