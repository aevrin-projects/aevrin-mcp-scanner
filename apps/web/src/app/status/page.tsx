import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

const DEFECTDOJO_URL = "https://defectdojo-production.up.railway.app";

export const metadata: Metadata = {
  title: "System Status — Aevrin",
  description: "Live availability checks for Aevrin's public web, API, authentication, and reporting services.",
};

async function checkUrl(url: string, headers?: HeadersInit): Promise<boolean> {
  try {
    const res = await fetch(url, { headers, signal: AbortSignal.timeout(5000), cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

export default async function StatusPage() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL!;
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!;
  const [apiUp, authUp, defectDojoUp] = await Promise.all([
    checkUrl(`${apiUrl}/health`),
    checkUrl(`${supabaseUrl}/auth/v1/health`, { apikey: supabaseKey }),
    checkUrl(`${DEFECTDOJO_URL}/login`),
  ]);

  const services = [
    { name: "Web", up: true }, // this page rendered, so web is up by definition
    { name: "API", up: apiUp },
    { name: "Authentication", up: authUp },
    { name: "OWASP-mapped reporting workspace", up: defectDojoUp },
  ];

  const allUp = services.every((s) => s.up);

  return (
    <div>
      <div className="mx-auto max-w-2xl px-6 py-16">
        <h1 className="text-2xl font-semibold tracking-tight">Status</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {allUp ? "All systems operational." : "Some systems are experiencing issues."}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Last checked {new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "long", timeZone: "UTC" }).format(new Date())}.
        </p>

        <div className="mt-8 flex flex-col gap-3">
          {services.map((s) => (
            <Card key={s.name}>
              <CardContent className="flex items-center justify-between py-4">
                <span className="text-sm font-medium">{s.name}</span>
                <Badge variant={s.up ? "secondary" : "destructive"}>
                  {s.up ? "Operational" : "Down"}
                </Badge>
              </CardContent>
            </Card>
          ))}
        </div>
        <p className="mt-6 text-xs leading-5 text-muted-foreground">
          These are live endpoint checks. A public incident-history feed is not currently configured.
        </p>
      </div>
      <SiteFooter />
    </div>
  );
}
