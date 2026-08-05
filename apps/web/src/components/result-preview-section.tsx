import { ArrowRight, GitPullRequest, ShieldAlert, TerminalSquare } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { Reveal } from "@/components/reveal";

// A real finding shape — the same fields the product actually stores and
// renders (tool, OWASP category, severity, file:line, remediation, EPSS).
// Sanitized sample values, real structure: nothing here claims a capability
// the scanner doesn't have.
const SAMPLE_FINDING = {
  severity: "Critical",
  title: "Command injection via unsanitized shell argument",
  tool: "semgrep",
  category: "MCP05 · Command Injection, Path Traversal, SSRF",
  location: "src/tools/run.ts:88",
  why: "A tool argument reaches a shell invocation without escaping, so a crafted value can execute arbitrary commands on the host running the server.",
  fix: "Use execFile with an argument array instead of interpolating into a shell string.",
};

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
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
            A finding tells you where it lives, why it matters, and how to close it.
          </h2>
          <p className="mt-3 text-muted-foreground">
            Not a severity label on its own. Every result carries the scanner that produced it, the exact
            location, the reasoning, and a concrete fix — plus exploitation-likelihood data where a CVE exists.
          </p>
        </Reveal>

        <div className="mt-10 grid items-start gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          {/* Finding card — mirrors the real finding-detail layout. */}
          <Reveal>
            <article className="overflow-hidden rounded-xl border border-border bg-card">
              <div className="flex flex-wrap items-center gap-2 border-b border-border px-5 py-3.5">
                <span className="rounded-full bg-severity-critical px-2 py-0.5 text-[11px] font-semibold tracking-wide text-severity-critical-foreground uppercase">
                  {SAMPLE_FINDING.severity}
                </span>
                <span className="rounded-md border border-border px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
                  {SAMPLE_FINDING.tool}
                </span>
                <span className="text-[11px] text-muted-foreground">{SAMPLE_FINDING.category}</span>
              </div>

              <div className="space-y-4 px-5 py-5">
                <h3 className="text-base font-medium text-foreground">{SAMPLE_FINDING.title}</h3>

                <div className="rounded-lg border border-border bg-background px-3 py-2.5">
                  <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">Location</p>
                  <p className="mt-1 font-mono text-[13px] break-all text-foreground">{SAMPLE_FINDING.location}</p>
                </div>

                <div>
                  <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                    Why it matters
                  </p>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">{SAMPLE_FINDING.why}</p>
                </div>

                <div>
                  <p className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">Remediation</p>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">{SAMPLE_FINDING.fix}</p>
                </div>

                <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
                  <span className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-2.5 py-1.5 text-xs font-medium text-primary-foreground">
                    <GitPullRequest className="size-3.5" aria-hidden="true" />
                    Fix It
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    Drafts a patch, re-runs <span className="font-mono">semgrep</span> to confirm it clears, then
                    opens a draft PR.
                  </span>
                </div>
              </div>
            </article>
          </Reveal>

          {/* Real CLI transcript — these are the actual commands and the
              actual output shape the CLI produces. */}
          <Reveal delay={80}>
            <div className="flex h-full flex-col overflow-hidden rounded-xl border border-border bg-card">
              <div className="flex items-center gap-2 border-b border-border px-5 py-3.5">
                <TerminalSquare className="size-3.5 text-muted-foreground" aria-hidden="true" />
                <span className="text-[11px] font-medium text-muted-foreground">Same result, from the terminal</span>
              </div>
              <pre className="flex-1 overflow-x-auto px-5 py-5 font-mono text-[12px] leading-6">
                <code>
                  <span className="text-muted-foreground">$ </span>
                  <span className="text-foreground">aevrin scan github.com/acme/mcp-server</span>
                  {"\n\n"}
                  <span className="text-muted-foreground">{"[✓] cloning\n"}</span>
                  <span className="text-muted-foreground">{"[✓] static analysis\n"}</span>
                  <span className="text-muted-foreground">{"[✓] secrets\n"}</span>
                  <span className="text-muted-foreground">{"[✓] dependencies\n"}</span>
                  <span className="text-muted-foreground">{"[✓] tool description check\n\n"}</span>
                  <span className="text-foreground">{"Score:  "}</span>
                  <span className="text-severity-high">{"56/100"}</span>
                  <span className="text-muted-foreground">{"  Significant risk\n\n"}</span>
                  <span className="text-severity-critical">{"CRITICAL  "}</span>
                  <span className="text-foreground">{"Command injection via unsanitized\n"}</span>
                  <span className="text-muted-foreground">{"          shell argument            src/tools/run.ts:88\n"}</span>
                  <span className="text-severity-high">{"HIGH      "}</span>
                  <span className="text-foreground">{"Path traversal in file read\n"}</span>
                  <span className="text-muted-foreground">{"          handler                  src/tools/read.ts:41\n\n"}</span>
                  <span className="text-muted-foreground">{"157 findings in test/fixture paths excluded\n"}</span>
                  <span className="text-muted-foreground">{"from the score."}</span>
                </code>
              </pre>
            </div>
          </Reveal>
        </div>

        <div className="mt-6 grid gap-3 md:grid-cols-3">
          {SURFACES.map((surface, index) => (
            <Reveal key={surface.name} delay={index * 60}>
              <div className="flex h-full flex-col rounded-xl border border-border bg-card p-5">
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
