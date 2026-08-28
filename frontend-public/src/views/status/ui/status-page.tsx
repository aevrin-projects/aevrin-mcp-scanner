"use client";

import { useEffect, useState } from "react";
import { SiteFooter } from "@/widgets/site-footer";
import { Badge } from "@/shared/ui/badge";
import { Card, CardContent } from "@/shared/ui/card";

// Optional: DefectDojo is a best-effort push target, so when this is unset
// the status page simply does not claim anything about it rather than
// reporting a component nobody deployed as down.
const DEFECTDOJO_URL = process.env.NEXT_PUBLIC_DEFECTDOJO_URL;

async function checkUrl(url: string, headers?: HeadersInit): Promise<boolean> {
  try {
    const res = await fetch(url, { headers, signal: AbortSignal.timeout(5000), cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

type Service = { name: string; up: boolean | null };

/**
 * Live checks, run from the visitor's own browser rather than the server:
 * this is a static export with no server to run them from, and a check
 * from the actual visitor's network is arguably the more honest signal
 * anyway (fewer false "up" reports from a healthy path that only Cloudflare's
 * edge can reach). See DECISIONS.md ADR-011.
 */
export function StatusPage() {
  const [services, setServices] = useState<Service[] | null>(null);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL!;
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
    const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!;

    Promise.all([
      checkUrl(`${apiUrl}/health`),
      checkUrl(`${supabaseUrl}/auth/v1/health`, { apikey: supabaseKey }),
      DEFECTDOJO_URL ? checkUrl(`${DEFECTDOJO_URL}/login`) : Promise.resolve(null),
    ]).then(([apiUp, authUp, defectDojoUp]) => {
      if (cancelled) return;
      setServices([
        { name: "Web", up: true }, // this page rendered, so web is up by definition
        { name: "API", up: apiUp },
        { name: "Authentication", up: authUp },
        // Listed only when it is actually deployed. Reporting a component
        // nobody configured as "down" would make a healthy system look
        // degraded.
        ...(defectDojoUp === null
          ? []
          : [{ name: "OWASP-mapped reporting workspace", up: defectDojoUp }]),
      ]);
      setCheckedAt(new Date());
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const allUp = services?.every((s) => s.up) ?? null;

  return (
    <div>
      <div className="mx-auto max-w-2xl px-6 py-16">
        <h1 className="text-2xl font-semibold tracking-tight">Status</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {allUp === null
            ? "Checking…"
            : allUp
              ? "All systems operational."
              : "Some systems are experiencing issues."}
        </p>
        {checkedAt ? (
          <p className="mt-1 text-xs text-muted-foreground">
            Last checked{" "}
            {new Intl.DateTimeFormat("en-US", {
              dateStyle: "medium",
              timeStyle: "long",
              timeZone: "UTC",
            }).format(checkedAt)}
            .
          </p>
        ) : null}

        <div className="mt-8 flex flex-col gap-3">
          {(services ?? [{ name: "Web", up: true }, { name: "API", up: null }, { name: "Authentication", up: null }]).map(
            (s) => (
              <Card key={s.name}>
                <CardContent className="flex items-center justify-between py-4">
                  <span className="text-sm font-medium">{s.name}</span>
                  <Badge variant={s.up === null ? "outline" : s.up ? "secondary" : "destructive"}>
                    {s.up === null ? "Checking" : s.up ? "Operational" : "Down"}
                  </Badge>
                </CardContent>
              </Card>
            ),
          )}
        </div>
        <p className="mt-6 text-xs leading-5 text-muted-foreground">
          These are live endpoint checks, run from your own browser. A public incident-history feed is not
          currently configured.
        </p>
      </div>
      <SiteFooter />
    </div>
  );
}
