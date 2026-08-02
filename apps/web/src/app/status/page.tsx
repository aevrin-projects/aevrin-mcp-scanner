import { SiteFooter } from "@/components/site-footer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

const DEFECTDOJO_URL = "https://defectdojo-production.up.railway.app";

async function checkUrl(url: string): Promise<boolean> {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(5000), cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

export default async function StatusPage() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL!;
  const [apiUp, defectDojoUp] = await Promise.all([
    checkUrl(`${apiUrl}/health`),
    checkUrl(`${DEFECTDOJO_URL}/login`),
  ]);

  const services = [
    { name: "Web", up: true }, // this page rendered, so web is up by definition
    { name: "API", up: apiUp },
    { name: "Compliance reporting (DefectDojo)", up: defectDojoUp },
  ];

  const allUp = services.every((s) => s.up);

  return (
    <div>
      <div className="mx-auto max-w-2xl px-6 py-16">
        <h1 className="text-2xl font-semibold tracking-tight">Status</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {allUp ? "All systems operational." : "Some systems are experiencing issues."}
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
      </div>
      <SiteFooter />
    </div>
  );
}
