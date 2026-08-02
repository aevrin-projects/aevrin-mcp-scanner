import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { SeverityBadge } from "@/components/severity-badge";
import { PricingSection } from "@/components/pricing-section";
import { InstallDocsSection } from "@/components/install-docs-section";
import { SiteFooter } from "@/components/site-footer";
import { ArrowRight } from "lucide-react";

const HOW_IT_WORKS = [
  { step: "1", title: "Scan", body: "Point Aevrin at a GitHub repo, a live MCP server, or a pasted config — from the CLI, the dashboard, or automatically via the Claude Code hook." },
  { step: "2", title: "Findings", body: "Ten established open-source security tools run in parallel, normalized against the OWASP MCP Top 10 — no vocabulary drift between the CLI and the dashboard." },
  { step: "3", title: "Score", body: "One number, 0–100, computed from severity-weighted findings — floor 0, so a server with real critical issues can't hide behind a partial scan." },
  { step: "4", title: "Fix", body: "Every finding ships with concrete remediation, triaged in the dashboard, exportable as a compliance report." },
];

export default function LandingPage() {
  return (
    <div>
      {/* Hero */}
      <section className="mx-auto max-w-6xl px-6 pb-16 pt-20 sm:pt-28">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
              Know what an MCP server can actually do before you install it.
            </h1>
            <p className="mt-4 text-lg text-muted-foreground">
              Aevrin scans MCP servers against the OWASP MCP Top 10 using established open-source
              security tools — one score, real findings, before it touches your machine.
            </p>
            <div className="mt-8 flex items-center gap-3">
              <Link href="/login" className={buttonVariants({ size: "lg" })}>
                Get started free
                <ArrowRight className="size-4" />
              </Link>
              <Link href="#install" className={buttonVariants({ size: "lg", variant: "outline" })}>
                Install the CLI
              </Link>
            </div>
          </div>

          <div className="rounded-lg border border-border bg-muted/40 p-5 font-mono text-sm">
            <div className="text-muted-foreground">$ aevrin scan github.com/owner/mcp-server</div>
            <div className="mt-2 flex flex-col gap-1 text-muted-foreground">
              <span>[✓] static analysis</span>
              <span>[✓] secrets</span>
              <span>[✓] dependencies</span>
              <span>[✓] tool description check</span>
              <span>[✓] aggregating</span>
            </div>
            <div className="mt-3">
              Score: <span className="font-semibold">62/100</span>{" "}
              <span className="text-muted-foreground">— Significant risk</span>
            </div>
            <div className="mt-4 flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <SeverityBadge severity="critical" />
                <span>Hardcoded secret — MCP01</span>
              </div>
              <div className="flex items-center gap-2">
                <SeverityBadge severity="high" />
                <span>subprocess shell=True — MCP05</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="border-t border-border bg-muted/20">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">How it works</h2>
          <div className="mt-10 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {HOW_IT_WORKS.map((item) => (
              <div key={item.step}>
                <div className="flex size-8 items-center justify-center rounded-full border border-border text-sm font-medium">
                  {item.step}
                </div>
                <h3 className="mt-3 font-medium">{item.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{item.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <PricingSection />
      <InstallDocsSection />
      <SiteFooter />
    </div>
  );
}
