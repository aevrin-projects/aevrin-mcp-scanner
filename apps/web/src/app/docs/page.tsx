import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, Braces, Gauge, ShieldCheck, TerminalSquare } from "lucide-react";
import { InstallDocsSection } from "@/components/install-docs-section";
import { SiteFooter } from "@/components/site-footer";
import { buttonVariants } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Documentation — Aevrin",
  description: "Install the Aevrin CLI, sign in securely, and configure the Claude Code hook.",
};

export default function DocsPage() {
  const docsUrl = process.env.NEXT_PUBLIC_DOCS_URL ?? "https://docs-production-3a0c.up.railway.app/docs";

  return (
    <div>
      <section className="border-b border-border/80 bg-muted/10">
        <div className="mx-auto max-w-5xl px-6 py-20 text-center sm:py-24">
          <div className="mx-auto flex size-12 items-center justify-center rounded-2xl border border-brand/25 bg-brand/10">
            <BookOpen className="size-5 text-brand-text" />
          </div>
          <h1 className="mt-6 text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
            Everything you need to run, understand, and govern Aevrin.
          </h1>
          <p className="mx-auto mt-5 max-w-3xl text-base leading-8 text-muted-foreground sm:text-lg">
            Explore installation, authentication, every scanner and target type, dashboard and CLI workflows,
            hook decisions, usage attribution, false-positive review, reports, API reference, security boundaries,
            and troubleshooting.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link href={docsUrl} className={buttonVariants({ size: "lg" })}>
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
              <div key={item.title} className="rounded-3xl border border-border/80 bg-background/85 p-5">
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
