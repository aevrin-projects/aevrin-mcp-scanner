import Link from "next/link";
import { ArrowRight, Braces, Gauge, ShieldCheck, TerminalSquare } from "lucide-react";
import { InstallDocsSection } from "@/widgets/install-docs";
import { SiteFooter } from "@/widgets/site-footer";
import { buttonVariants } from "@/shared/ui/button";

export function CliPage() {
  return (
    <div>
      <section className="border-b border-border/80 bg-muted/10">
        <div className="mx-auto max-w-5xl px-6 py-20 text-center sm:py-24">
          <div className="mx-auto flex size-12 items-center justify-center rounded-xl border border-brand/25 bg-brand/10">
            <TerminalSquare className="size-5 text-brand-text" />
          </div>
          <h1 className="mt-6 text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
            Install, authenticate, and run Aevrin from your terminal.
          </h1>
          <p className="mx-auto mt-5 max-w-3xl text-base leading-8 text-muted-foreground sm:text-lg">
            Use this focused setup guide for the CLI and Claude Code hook. The complete documentation covers every
            scanner, target, dashboard workflow, usage event, report, API contract, and troubleshooting path.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link href="/docs" className={buttonVariants({ size: "lg" })}>
              Open complete documentation
              <ArrowRight className="size-4" />
            </Link>
            <a href="mailto:support@aevrin.net" className={buttonVariants({ size: "lg", variant: "outline" })}>
              Contact support
            </a>
          </div>
          <div className="mt-12 grid gap-4 text-left sm:grid-cols-2 lg:grid-cols-4">
            {[
              { icon: TerminalSquare, title: "CLI and CI", body: "Commands, flags, JSON, exit codes, device login, and automation gates." },
              { icon: ShieldCheck, title: "Coverage", body: "What every scanner catches, what it skips, and how incomplete results behave." },
              { icon: Gauge, title: "Dashboard", body: "History, usage, scan sources, findings, false positives, and exports." },
              { icon: Braces, title: "API and hooks", body: "Endpoint contracts, hook cache decisions, overrides, auth, and safe execution." },
            ].map((item) => (
              <div key={item.title} className="rounded-xl border border-border/80 bg-background/85 p-5">
                <item.icon className="size-5 text-brand-text" />
                <h2 className="mt-4 font-medium text-foreground">{item.title}</h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
      <InstallDocsSection headingLevel="h2" />
      <SiteFooter />
    </div>
  );
}
