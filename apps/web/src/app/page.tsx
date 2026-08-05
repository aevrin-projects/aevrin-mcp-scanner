import Link from "next/link";
import { headers } from "next/headers";
import { ArrowRight, Eye, FileWarning, KeyRound, PackageOpen, TerminalSquare } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { PricingSection } from "@/components/pricing-section";
import { InstallDocsSection } from "@/components/install-docs-section";
import { MethodologySection } from "@/components/methodology-section";
import { ResultPreviewSection } from "@/components/result-preview-section";
import { HeroScanVisual } from "@/components/hero-scan-visual";
import { SiteFooter } from "@/components/site-footer";
import { Reveal } from "@/components/reveal";

// The concrete reasons an MCP server is worth reviewing before install. Each
// maps to a real OWASP MCP category the scanner actually checks — this is a
// risk explanation, not a feature list.
const RISKS = [
  {
    icon: Eye,
    title: "It ships a description the model obeys",
    body: "A tool description is instructions to your agent. Text hidden inside it can redirect behaviour without ever touching your code.",
    tag: "MCP02 · Tool poisoning",
  },
  {
    icon: KeyRound,
    title: "It runs with your credentials",
    body: "Servers routinely hold tokens for the systems they reach. A leaked or over-scoped credential inherits everything you granted.",
    tag: "MCP01 · Token mismanagement",
  },
  {
    icon: TerminalSquare,
    title: "It executes on your machine",
    body: "A stdio server is a local process. An unescaped argument reaching a shell is command execution on the host.",
    tag: "MCP05 · Command injection",
  },
  {
    icon: PackageOpen,
    title: "It can change after you trust it",
    body: "Tool definitions can drift after install, and dependencies carry their own known vulnerabilities.",
    tag: "MCP04 · Rug pull",
  },
];

export default async function LandingPage() {
  const headersList = await headers();
  const signedIn = Boolean(headersList.get("x-aevrin-user-email"));
  const primaryHref = signedIn ? "/dashboard" : "/login";

  return (
    <div className="bg-background">
      {/* Hero — single column and centred. The previous version stacked a
          giant "AEVRIN" wordmark (already present in the navbar) above the
          headline and paired it with a mock product panel; both competed
          with the real product output now shown directly below. */}
      <section className="relative overflow-hidden border-b border-border">
        <div className="absolute inset-x-0 top-0 h-[520px] bg-[radial-gradient(circle_at_50%_0%,rgba(121,192,255,0.10),transparent_60%)]" />
        <div className="security-mesh absolute inset-0 opacity-30" aria-hidden="true" />

        <div className="relative mx-auto max-w-3xl px-6 pt-16 pb-6 text-center lg:pt-20 lg:pb-8">
          <Reveal>
            <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-[11px] text-muted-foreground">
              <span className="relative flex size-1.5">
                <span className="absolute inline-flex size-full rounded-full bg-brand opacity-70 motion-safe:animate-ping" />
                <span className="relative inline-flex size-1.5 rounded-full bg-brand" />
              </span>
              Security review for MCP servers
            </span>
          </Reveal>

          <Reveal delay={70}>
            <h1 className="mt-6 text-4xl font-semibold tracking-tight text-balance sm:text-5xl lg:text-[3.5rem] lg:leading-[1.05]">
              Know what an MCP server can do before you install it.
            </h1>
          </Reveal>

          <Reveal delay={130}>
            <p className="mx-auto mt-5 max-w-xl text-base leading-relaxed text-muted-foreground">
              Aevrin scans a repository, a live server, or a pasted config with established open-source
              security tools — then tells you what it found, what it couldn&apos;t check, and how to fix it.
            </p>
          </Reveal>

          <Reveal delay={190}>
            <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
              <Link href={primaryHref} className={buttonVariants({ size: "lg", className: "h-11 px-6" })}>
                {signedIn ? "Open the dashboard" : "Start free"}
                <ArrowRight className="size-4" />
              </Link>
              <Link
                href="#install"
                className={buttonVariants({ size: "lg", variant: "outline", className: "h-11 px-6" })}
              >
                Install the CLI
              </Link>
            </div>
          </Reveal>

          <Reveal delay={250}>
            <p className="mt-6 text-xs text-muted-foreground">
              Free plan needs no card. Nothing renews automatically.
            </p>
          </Reveal>
        </div>

        <div className="relative mx-auto max-w-[1500px] px-6 pb-16 lg:px-10">
          <HeroScanVisual />
        </div>
      </section>

      {/* Why this matters — concrete risk, each tied to a real category the
          scanner checks, rather than abstract "why teams adopt it" copy. */}
      <section className="border-b border-border">
        <div className="mx-auto max-w-[1500px] px-6 py-24 lg:px-10 xl:px-14">
          <Reveal className="max-w-3xl">
            <span className="text-xs font-medium tracking-wide text-brand-text uppercase">The risk</span>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
              An MCP server is code, credentials, and instructions your agent trusts.
            </h2>
            <p className="mt-3 text-muted-foreground">
              Installing one grants real capability on your machine and in the systems it reaches. These are the
              failure modes Aevrin looks for.
            </p>
          </Reveal>

          <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {RISKS.map((risk, index) => (
              <Reveal key={risk.title} delay={index * 60}>
                <div className="flex h-full flex-col rounded-xl border border-border bg-card p-5">
                  <risk.icon className="size-4 text-brand-text" aria-hidden="true" />
                  <h3 className="mt-3 text-[15px] font-medium text-balance">{risk.title}</h3>
                  <p className="mt-2 flex-1 text-[13px] leading-relaxed text-muted-foreground">{risk.body}</p>
                  <span className="mt-4 font-mono text-[11px] text-muted-foreground">{risk.tag}</span>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <ResultPreviewSection />

      {/* Honest-coverage promise — the product's actual differentiator, so it
          gets its own moment rather than being one bullet in a feature grid. */}
      <section className="border-b border-border">
        <div className="mx-auto max-w-[1500px] px-6 py-24 lg:px-10 xl:px-14">
          <Reveal>
            <div className="mx-auto flex max-w-3xl flex-col items-center gap-4 text-center">
              <FileWarning className="size-5 text-brand-text" aria-hidden="true" />
              <h2 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
                A clean result never quietly means &ldquo;we didn&apos;t look&rdquo;.
              </h2>
              <p className="text-muted-foreground">
                If a scanner fails, a stage is skipped, or a target type can&apos;t be source-scanned, the result
                says so — on the page, in the CLI, and in the exported report. Partial coverage stays labelled
                partial instead of being rounded up to a passing score.
              </p>
            </div>
          </Reveal>
        </div>
      </section>

      <MethodologySection />
      <PricingSection />
      <InstallDocsSection />
      <SiteFooter />
    </div>
  );
}
