"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

/**
 * Reports a pageview on every client-side navigation.
 *
 * `usePathname` rather than a script tag because this is a single-page app;
 * a plain analytics snippet fires once on hard load and then never again as
 * someone moves between routes, which would make every internal page look
 * unvisited.
 *
 * Fire-and-forget with `keepalive` so a report still lands when the click
 * that triggered it is also navigating away.
 *
 * Posts to the API rather than a Next route handler: the write needs the
 * Supabase service-role key, and putting that on the public-facing web
 * service would widen the blast radius of any SSRF or RCE there to full
 * database access.
 */
export function PageTracker() {
  const pathname = usePathname();
  const lastReported = useRef<string | null>(null);

  useEffect(() => {
    if (!pathname || lastReported.current === pathname) return;
    lastReported.current = pathname;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!apiUrl) return;

    void fetch(`${apiUrl}/events/pageview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: pathname, referrer: document.referrer || null }),
      keepalive: true,
    }).catch(() => {
      // A failed pageview is never worth surfacing to a visitor.
    });
  }, [pathname]);

  return null;
}
