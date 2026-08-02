import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { SeverityBadge } from "@/components/severity-badge";
import { PricingSection } from "@/components/pricing-section";
import { InstallDocsSection } from "@/components/install-docs-section";
import { SiteFooter } from "@/components/site-footer";
import { Reveal } from "@/components/reveal";
import { ArrowRight, ScanLine, ListChecks, Gauge, Wrench } from "lucide-react";

const HOW_IT_WORKS = [
  {
    step: "01",
    title: "Scan",
    icon: ScanLine,
    body: "Point Aevrin at a GitHub repo, a live MCP server, or a pasted config — from the CLI, the dashboard, or automatically via the Claude Code hook.",
  },
  {
    step: "02",
    title: "Findings",
    icon: ListChecks,
    body: "Ten established open-source security tools run in parallel, normalized against the OWASP MCP Top 10 — no vocabulary drift between the CLI and the dashboard.",
  },
  {
    step: "03",
    title: "Score",
    icon: Gauge,
    body: "One number, 0–100, computed from severity-weighted findings — floor 0, so a server with real critical issues can't hide behind a partial scan.",
  },
  {
    step: "04",
    title: "Fix",
    icon: Wrench,
    body: "Every finding ships with concrete remediation, triaged in the dashboard, exportable as a compliance report.",
  },
];

export default function LandingPage() {
  return (
    <div>
      {/* Hero */}
      <section className="mx-auto max-w-6xl px-6 pb-16 pt-20 sm:pt-28">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <Reveal>
              <span className="inline-flex items-center rounded-full border border-border px-3 py-1 text-xs text-muted-foreground">
                Aevrin MCP Scanner
              </span>
            </Reveal>
            <Reveal delay={80}>
              <h1 className="mt-5 text-3xl font-semibold tracking-tight text-balance sm:text-5xl">
                MCP servers move fast.
                <br />
                Security should too.
              </h1>
            </Reveal>
            <Reveal delay={160}>
              <p className="mt-5 max-w-md text-lg text-muted-foreground">
                Scan any MCP server against the OWASP MCP Top 10 before you install it — real
                findings from established open-source tools, not a vague trust score.
              </p>
            </Reveal>
            <Reveal delay={240}>
              <div className="mt-8 flex items-center gap-3">
                <Link href="/login" className={buttonVariants({ size: "lg" })}>
                  Get started free
                  <ArrowRight className="size-4" />
                </Link>
                <Link href="#install" className={buttonVariants({ size: "lg", variant: "outline" })}>
                  Install the CLI
                </Link>
              </div>
            </Reveal>
          </div>

          <Reveal delay={120}>
            <div className="rounded-xl border border-border bg-muted/40 p-5 font-mono text-sm shadow-sm">
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
          </Reveal>
        </div>
      </section>

      {/* How it works */}
      <section id="product" className="border-t border-border bg-muted/20">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <Reveal>
            <span className="text-xs font-medium tracking-wide text-brand uppercase">How it works</span>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
              From clone to verdict, four steps.
            </h2>
          </Reveal>
          <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {HOW_IT_WORKS.map((item, i) => (
              <Reveal key={item.step} delay={i * 80}>
                <div className="h-full rounded-xl border border-border bg-background p-5">
                  <div className="flex items-start justify-between">
                    <span className="font-mono text-xs text-brand">{item.step}</span>
                    <item.icon className="size-4 text-muted-foreground" />
                  </div>
                  <h3 className="mt-4 font-medium">{item.title}</h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">{item.body}</p>
                </div>
              </Reveal>
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
