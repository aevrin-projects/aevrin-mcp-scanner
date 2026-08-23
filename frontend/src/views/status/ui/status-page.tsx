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

export async function StatusPage() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL!;
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!;
  const [apiUp, authUp, defectDojoUp] = await Promise.all([
    checkUrl(`${apiUrl}/health`),
    checkUrl(`${supabaseUrl}/auth/v1/health`, { apikey: supabaseKey }),
    DEFECTDOJO_URL ? checkUrl(`${DEFECTDOJO_URL}/login`) : Promise.resolve(null),
  ]);

  const services = [
    { name: "Web", up: true }, // this page rendered, so web is up by definition
    { name: "API", up: apiUp },
    { name: "Authentication", up: authUp },
    // Listed only when it is actually deployed. Reporting a component nobody
    // configured as "down" would make a healthy system look degraded.
    ...(defectDojoUp === null
      ? []
      : [{ name: "OWASP-mapped reporting workspace", up: defectDojoUp }]),
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
