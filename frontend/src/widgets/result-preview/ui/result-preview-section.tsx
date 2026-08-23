import { ArrowRight, GitPullRequest, ShieldAlert, TerminalSquare } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/shared/ui/button";
import { Reveal } from "@/shared/ui/reveal";

const SURFACES = [
  {
    icon: ShieldAlert,
    name: "Dashboard",
    body: "Triage findings, see what each stage actually covered, and export an OWASP-mapped report.",
    href: "/login",
    cta: "Open the workspace",
  },
  {
    icon: TerminalSquare,
    name: "CLI",
    body: "Same scanners, same vocabulary, in your terminal or CI. Fails the build on a threshold you set.",
    href: "/cli",
    cta: "Install the CLI",
  },
  {
    icon: GitPullRequest,
    name: "Claude Code hook",
    body: "Blocks or warns on an unsafe MCP install before it lands on a workstation.",
    href: "/integrations",
    cta: "Add the hook",
  },
];

export function ResultPreviewSection() {
  return (
    <section className="border-b border-border">
      <div className="mx-auto max-w-[1500px] px-6 py-24 lg:px-10 xl:px-14">
        <Reveal className="max-w-3xl">
          <span className="text-xs font-medium tracking-wide text-brand-text uppercase">What you get back</span>
          <h2 className="display-md mt-3">
            A finding tells you where it lives, why it matters, and how to close it.
          </h2>
          <p className="mt-3 text-muted-foreground">
            Not a severity label on its own. Every result carries the scanner that produced it, the exact
            location, the reasoning, and a concrete fix, plus exploitation-likelihood data where a CVE exists.
          </p>
        </Reveal>

        <div className="mt-10 grid items-stretch gap-6 md:grid-cols-3">
          {SURFACES.map((surface, index) => (
            <Reveal key={surface.name} delay={index * 60}>
              <div className="flex h-full flex-col rounded-lg border border-border bg-card p-5">
                <div className="flex items-center gap-2">
                  <surface.icon className="size-4 text-foreground" aria-hidden="true" />
                  <h3 className="text-[15px] font-medium">{surface.name}</h3>
                </div>
                <p className="mt-2 flex-1 text-[13px] leading-relaxed text-muted-foreground">{surface.body}</p>
                <Link
                  href={surface.href}
                  className={buttonVariants({ variant: "outline", size: "sm", className: "mt-4 w-fit" })}
                >
                  {surface.cta}
                  <ArrowRight className="size-3.5" />
                </Link>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
