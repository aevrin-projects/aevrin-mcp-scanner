import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  FileSearch,
  GitBranch,
  ScanSearch,
  ShieldAlert,
  ShieldCheck,
  TerminalSquare,
  Waypoints,
  Wrench,
} from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { PricingSection } from "@/components/pricing-section";
import { InstallDocsSection } from "@/components/install-docs-section";
import { SiteFooter } from "@/components/site-footer";
import { Reveal } from "@/components/reveal";
import { createClient } from "@/lib/supabase/server";

const PILLARS = [
  {
    title: "Real scanner evidence",
    body: "Aevrin normalizes findings from the actual open-source tools in the scan pipeline. The CLI, API, and dashboard read the same vocabulary.",
    icon: ScanSearch,
  },
  {
    title: "Honest completeness",
    body: "Partial and failed stages are surfaced directly so a clean findings list never hides missing coverage, broken tooling, or network limits.",
    icon: ShieldAlert,
  },
  {
    title: "Actionable remediation",
    body: "Each finding is framed around what happened, why it matters, how to fix it, and how to verify the fix with a repeat scan.",
    icon: Wrench,
  },
  {
    title: "Developer workflow coverage",
    body: "Use the dashboard for guided scans, the CLI for local review, and the Claude Code hook for pre-install decisions.",
    icon: Waypoints,
  },
] as const;

const QUESTIONS = [
  "What needs my attention right now?",
  "What was scanned, how completely, and when?",
  "Why is this finding dangerous?",
  "How do I fix it?",
  "How do I verify the fix actually worked?",
];

const ROLLOUT = [
  {
    title: "Start with a dashboard scan",
    body: "Review target type, coverage, stage failures, and remediation without installing anything locally first.",
    icon: ShieldCheck,
  },
  {
    title: "Move to CLI for repeated checks",
    body: "Run the same scanner vocabulary from your own terminal when you want fast local confirmation before merge or install.",
    icon: TerminalSquare,
  },
  {
    title: "Add the hook for gatekeeping",
    body: "Use the Claude Code pre-install check when you want unsafe MCP adds to warn or block before they touch a workstation.",
    icon: Bot,
  },
] as const;

export default async function LandingPage() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  const signedIn = Boolean(data?.claims);
  const primaryHref = signedIn ? "/dashboard" : "/login";

  return (
    <div className="bg-background">
      <section className="relative overflow-hidden border-b border-border/80">
        <div className="absolute inset-x-0 top-0 h-[560px] bg-[radial-gradient(circle_at_top_left,rgba(188,230,10,0.18),transparent_42%),radial-gradient(circle_at_top_right,rgba(255,255,255,0.08),transparent_28%)] dark:bg-[radial-gradient(circle_at_top_left,rgba(188,230,10,0.12),transparent_38%),radial-gradient(circle_at_top_right,rgba(255,255,255,0.04),transparent_24%)]" />
        <div className="security-mesh absolute inset-0 opacity-45" aria-hidden="true" />
        <div className="security-orb security-orb-one" aria-hidden="true" />
        <div className="security-orb security-orb-two" aria-hidden="true" />
        <div className="hero-scan-beam" aria-hidden="true" />
        <div className="relative mx-auto max-w-[1600px] px-6 pb-20 pt-16 lg:px-10 lg:pb-24 lg:pt-20 xl:px-14">
          <div className="grid gap-10 xl:grid-cols-[minmax(0,0.78fr)_minmax(600px,1.22fr)] xl:items-center">
            <div className="space-y-8">
              <Reveal>
                <div className="inline-flex items-center gap-3 rounded-full border border-border/80 bg-background/80 px-4 py-2">
                  <Image src="/logo.png" alt="" width={20} height={22} priority />
                  <span className="text-[0.72rem] font-medium tracking-[0.24em] text-muted-foreground uppercase">
                    Aevrin MCP Scanner
                  </span>
                </div>
              </Reveal>

              <div className="space-y-5">
                <Reveal delay={70}>
                  <p className="text-[2.8rem] leading-none font-semibold tracking-[0.18em] text-foreground uppercase sm:text-[4.5rem] lg:text-[5.3rem]">
                    Aevrin
                  </p>
                </Reveal>
                <Reveal delay={130}>
                  <h1 className="max-w-4xl text-4xl font-semibold tracking-tight text-balance text-foreground sm:text-5xl lg:text-6xl">
                    Security review for MCP servers, with honest coverage and actionable fixes.
                  </h1>
                </Reveal>
                <Reveal delay={190}>
                  <p className="max-w-3xl text-base leading-8 text-muted-foreground sm:text-lg">
                    Review source repositories, live MCP servers, or pasted configuration through the
                    same authenticated product workspace your team will use to triage, verify, and
                    repeat scans. No invented trend lines. No fake confidence.
                  </p>
                </Reveal>
              </div>

              <Reveal delay={250}>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <Link href={primaryHref} className={buttonVariants({ size: "lg" })}>
                    {signedIn ? "Open the dashboard" : "Open the product"}
                    <ArrowRight className="size-4" />
                  </Link>
                  <Link href="#install" className={buttonVariants({ size: "lg", variant: "outline" })}>
                    Install the CLI
                  </Link>
                </div>
              </Reveal>

              <Reveal delay={310}>
                <div className="grid gap-4 md:grid-cols-3">
                  <HeroCallout
                    title="Coverage is explicit"
                    body="Complete, partial, failed, skipped, and stale states are called out instead of hidden."
                    icon={<FileSearch className="size-4 text-brand-text" />}
                  />
                  <HeroCallout
                    title="Findings stay operational"
                    body="Evidence, remediation, OWASP MCP mapping, and repeat-scan verification live in one flow."
                    icon={<ShieldAlert className="size-4 text-brand-text" />}
                  />
                  <HeroCallout
                    title="Built for real rollout"
                    body="Use the dashboard, CLI, and Claude Code hook together without drifting into separate products."
                    icon={<GitBranch className="size-4 text-brand-text" />}
                  />
                </div>
              </Reveal>
            </div>

            <Reveal delay={140} className="h-full">
              <div className="motion-float-card relative overflow-hidden rounded-[30px] border border-border/80 bg-card/75 p-3 shadow-2xl shadow-black/15 backdrop-blur-sm sm:p-5">
                <div className="preview-scan-sweep" aria-hidden="true" />
                <div className="rounded-[26px] border border-border/80 bg-background/92 p-4 sm:p-5">
                  <div className="flex flex-col gap-4 border-b border-border/80 pb-5 sm:flex-row sm:items-start sm:justify-between">
                    <div className="space-y-1">
                      <p className="text-xs font-medium tracking-[0.18em] text-muted-foreground uppercase">
                        Authenticated workflow preview
                      </p>
                      <h2 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">
                        Review the available evidence before a server gets installed.
                      </h2>
                    </div>
                    <div className="rounded-full border border-brand/30 bg-brand/10 px-3 py-1 text-xs font-medium text-foreground">
                      Security-first workspace
                    </div>
                  </div>

                  <div className="mt-5 grid gap-4 sm:grid-cols-2">
                    <PreviewCard
                      eyebrow="New scan"
                      title="Start from the target you actually have"
                      body="Source repository, live MCP server, or pasted config input. Aevrin explains the trade-off in coverage before you launch the scan."
                    >
                      <ul className="space-y-2 text-sm text-muted-foreground">
                        <li>Source repo: broadest code, dependency, and secret coverage</li>
                        <li>Live MCP server: runtime install decision, reduced static visibility</li>
                        <li>Pasted config: fastest route for triage and follow-up</li>
                      </ul>
                    </PreviewCard>

                    <PreviewCard
                      eyebrow="Result state"
                      title="Partial scans stay partial"
                      body="Coverage notes, skipped stages, and failed scanners remain visible on the result page so remediation decisions stay grounded."
                    >
                      <div className="space-y-2 text-sm">
                        <PreviewRow label="Status" value="Partial coverage" tone="brand" />
                        <PreviewRow label="Stage summary" value="Completed, skipped, and failed stages" />
                        <PreviewRow label="Next action" value="Review limitations before approving install" />
                      </div>
                    </PreviewCard>

                    <PreviewCard
                      eyebrow="Finding detail"
                      title="Fixes are not just labels"
                      body="A finding page explains where the issue lives, why it matters, how to fix it, and how to verify the fix with a repeat scan."
                    >
                      <div className="space-y-2 text-sm">
                        <PreviewRow label="Evidence" value="File, line, manifest field, or tool surface" />
                        <PreviewRow label="Risk" value="OWASP MCP category and source scanner" />
                        <PreviewRow label="Verification" value="Repeat the comparable scan after remediation" />
                      </div>
                    </PreviewCard>

                    <PreviewCard
                      eyebrow="Rollout path"
                      title="One product across browser, terminal, and hook"
                      body="Install the CLI, log in with device flow, and use the Claude Code hook only where automated pre-install checks fit your process."
                    >
                      <div className="space-y-3">
                        <div className="rounded-2xl border border-border bg-background px-4 py-3 font-mono text-xs leading-6 text-foreground">
                          aevrin login{"\n"}aevrin scan github.com/owner/mcp-server --upload
                        </div>
                        <p className="text-sm text-muted-foreground">
                          API keys stay reserved for CI and other non-interactive environments.
                        </p>
                      </div>
                    </PreviewCard>
                  </div>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-[1500px] px-6 py-20 lg:px-10 xl:px-14">
        <Reveal>
          <span className="text-xs font-medium tracking-wide text-brand-text uppercase">Why teams adopt it</span>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
            The product is designed around decision quality, not empty dashboard filler.
          </h2>
        </Reveal>
        <div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {PILLARS.map((item, index) => (
            <Reveal key={item.title} delay={index * 80}>
              <div className="interactive-lift h-full rounded-[28px] border border-border/80 bg-card/70 p-6">
                <div className="flex size-11 items-center justify-center rounded-2xl border border-brand/25 bg-brand/10">
                  <item.icon className="size-5 text-brand-text" />
                </div>
                <h3 className="mt-5 text-xl font-semibold tracking-tight text-foreground">{item.title}</h3>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">{item.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="border-y border-border/80 bg-muted/10">
        <div className="mx-auto max-w-[1500px] px-6 py-20 lg:px-10 xl:px-14">
          <div className="grid gap-8 xl:grid-cols-[1.05fr_0.95fr]">
            <Reveal>
              <div className="rounded-[30px] border border-border/80 bg-background/90 p-8">
                <span className="text-xs font-medium tracking-wide text-brand-text uppercase">What users need answered</span>
                <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
                  The product is organized around the questions security reviews actually produce.
                </h2>
                <div className="mt-8 space-y-3">
                  {QUESTIONS.map((question, index) => (
                    <div
                      key={question}
                      className="interactive-lift flex items-start gap-4 rounded-2xl border border-border/80 bg-card/65 px-4 py-4"
                    >
                      <div className="flex size-8 items-center justify-center rounded-full border border-brand/25 bg-brand/10 text-sm font-medium text-foreground">
                        {index + 1}
                      </div>
                      <p className="pt-1 text-sm leading-7 text-foreground sm:text-base">{question}</p>
                    </div>
                  ))}
                </div>
              </div>
            </Reveal>

            <Reveal delay={120}>
              <div className="grid gap-5">
                {ROLLOUT.map((item, index) => (
                  <div key={item.title} className="interactive-lift rounded-[28px] border border-border/80 bg-background/90 p-6">
                    <div className="flex items-center gap-3">
                      <div className="flex size-11 items-center justify-center rounded-2xl border border-brand/25 bg-brand/10">
                        <item.icon className="size-5 text-brand-text" />
                      </div>
                      <h3 className="text-lg font-semibold tracking-tight text-foreground">{item.title}</h3>
                    </div>
                    <p className="mt-4 text-sm leading-7 text-muted-foreground">{item.body}</p>
                    {index === 0 ? (
                      <div className="mt-5">
                        <Link href={primaryHref} className={buttonVariants({ variant: "outline" })}>
                          Open authenticated workspace
                        </Link>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      <PricingSection />
      <InstallDocsSection />
      <SiteFooter />
    </div>
  );
}

function HeroCallout({
  title,
  body,
  icon,
}: {
  title: string;
  body: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="interactive-lift rounded-3xl border border-border/80 bg-card/65 p-5">
      <div className="flex items-center gap-3">
        <div className="flex size-9 items-center justify-center rounded-2xl border border-brand/25 bg-brand/10">
          {icon}
        </div>
        <p className="text-sm font-medium text-foreground">{title}</p>
      </div>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">{body}</p>
    </div>
  );
}

function PreviewCard({
  eyebrow,
  title,
  body,
  children,
}: {
  eyebrow: string;
  title: string;
  body: string;
  children: React.ReactNode;
}) {
  return (
    <div className="interactive-lift rounded-[24px] border border-border/80 bg-card/70 p-5">
      <p className="text-[0.7rem] font-medium tracking-[0.18em] text-muted-foreground uppercase">{eyebrow}</p>
      <h3 className="mt-2 text-lg font-semibold tracking-tight text-foreground">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{body}</p>
      <div className="mt-4">{children}</div>
    </div>
  );
}

function PreviewRow({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "brand";
}) {
  return (
    <div className="flex flex-col gap-1 rounded-2xl border border-border/80 bg-background/90 px-4 py-3">
      <span className="text-[0.68rem] font-medium tracking-[0.16em] text-muted-foreground uppercase">
        {label}
      </span>
      <span className={tone === "brand" ? "text-sm font-medium text-foreground" : "text-sm text-foreground"}>
        {value}
      </span>
    </div>
  );
}
