import { Check, Minus } from "lucide-react";
import { OWASP_CATEGORY_LABELS, STAGE_LABELS, STAGE_ORDER } from "@/lib/types";
import { Reveal } from "@/components/reveal";

// The scanners that actually run in the pipeline (see packages/scanner-core
// adapters). Listed by name because "which tools produced this" is exactly
// the question a security reviewer asks first — and because every one is a
// real, auditable open-source project rather than a black box.
const SCANNERS = [
  { name: "Semgrep", role: "Static analysis across the OWASP rulesets" },
  { name: "Bandit", role: "Python-specific security linting" },
  { name: "Gitleaks", role: "Committed secrets and credential patterns" },
  { name: "TruffleHog", role: "Secret detection with live credential verification" },
  { name: "OSV-Scanner", role: "Dependency advisories from the OSV database" },
  { name: "Trivy", role: "Vulnerability and misconfiguration scanning" },
  { name: "OpenSSF Scorecard", role: "Repository supply-chain health signals" },
  { name: "mcp-shield", role: "MCP tool-description and manifest inspection" },
];

// Honest coverage matrix. A live server or a pasted config genuinely cannot
// be source-scanned — saying so plainly is the product's whole positioning,
// so the landing page states it rather than implying uniform coverage.
const COVERAGE: { stage: string; repo: boolean; server: boolean; config: boolean }[] = [
  { stage: "Source code analysis", repo: true, server: false, config: false },
  { stage: "Secret detection", repo: true, server: false, config: false },
  { stage: "Dependency advisories", repo: true, server: false, config: false },
  { stage: "Supply-chain health", repo: true, server: false, config: false },
  { stage: "Declared-tool inspection", repo: true, server: true, config: true },
  { stage: "Manifest and auth checks", repo: true, server: true, config: true },
];

const STAGE_DETAIL: Record<string, string> = {
  cloning: "Fetch the target into isolated, temporary scan storage.",
  static_analysis: "Run Semgrep and Bandit against the source.",
  secrets: "Sweep for committed credentials with Gitleaks and TruffleHog.",
  dependencies: "Resolve advisories, then weight them by EPSS and CISA KEV.",
  tool_description_check: "Inspect declared MCP tools for hidden instructions.",
  aggregating: "Deduplicate, group by root cause, and score.",
};

export function MethodologySection() {
  return (
    <section className="mx-auto max-w-[1500px] px-6 py-24 lg:px-10 xl:px-14">
      <Reveal className="text-center">
        <span className="text-xs font-medium tracking-wide text-brand-text uppercase">Methodology</span>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
          What gets checked, by which tool, and what stays uncovered.
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-muted-foreground">
          Every finding traces back to a named open-source scanner and an OWASP MCP category. Coverage that
          isn&apos;t possible for a given target type is stated, not implied.
        </p>
      </Reveal>

      <div className="mt-12 grid gap-6 lg:grid-cols-2">
        <Reveal>
          <div className="h-full rounded-xl border border-border bg-card p-6">
            <h3 className="text-[15px] font-medium">Mapped to the OWASP MCP Top 10</h3>
            <p className="mt-1.5 text-sm text-muted-foreground">
              Findings carry the category they belong to, so results line up with an existing review process.
            </p>
            <ul className="mt-5 flex flex-col gap-2.5">
              {Object.entries(OWASP_CATEGORY_LABELS).map(([code, label]) => (
                <li key={code} className="flex items-start gap-3 text-[13px]">
                  <span className="mt-px shrink-0 rounded border border-border px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
                    {code}
                  </span>
                  <span className="text-muted-foreground">{label}</span>
                </li>
              ))}
            </ul>
          </div>
        </Reveal>

        <Reveal delay={80}>
          <div className="h-full rounded-xl border border-border bg-card p-6">
            <h3 className="text-[15px] font-medium">The scanners doing the work</h3>
            <p className="mt-1.5 text-sm text-muted-foreground">
              Established open-source tools, normalized into one vocabulary across the dashboard, CLI, and hook.
            </p>
            <ul className="mt-5 flex flex-col gap-3">
              {SCANNERS.map((scanner) => (
                <li key={scanner.name} className="flex flex-col gap-0.5">
                  <span className="font-mono text-[13px] text-foreground">{scanner.name}</span>
                  <span className="text-[13px] text-muted-foreground">{scanner.role}</span>
                </li>
              ))}
            </ul>
          </div>
        </Reveal>
      </div>

      <Reveal className="mt-6">
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="text-[15px] font-medium">Coverage by target type</h3>
          <p className="mt-1.5 text-sm text-muted-foreground">
            A live endpoint or a pasted configuration can&apos;t be source-scanned. Aevrin says so before you
            start, and the result page repeats it afterwards.
          </p>
          <div className="mt-5 overflow-x-auto" tabIndex={0} aria-label="Coverage by target type">
            <table className="w-full min-w-[560px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-border text-left">
                  <th scope="col" className="py-2.5 pr-4 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                    Check
                  </th>
                  <th scope="col" className="py-2.5 px-4 text-center text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                    Repository
                  </th>
                  <th scope="col" className="py-2.5 px-4 text-center text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                    Live server
                  </th>
                  <th scope="col" className="py-2.5 pl-4 text-center text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                    Pasted config
                  </th>
                </tr>
              </thead>
              <tbody>
                {COVERAGE.map((row) => (
                  <tr key={row.stage} className="border-b border-border/60 last:border-0">
                    <td className="py-3 pr-4 text-muted-foreground">{row.stage}</td>
                    {[row.repo, row.server, row.config].map((covered, index) => (
                      <td key={index} className="px-4 py-3 text-center">
                        {covered ? (
                          <>
                            <Check className="mx-auto size-4 text-foreground" aria-hidden="true" />
                            <span className="sr-only">Covered</span>
                          </>
                        ) : (
                          <>
                            <Minus className="mx-auto size-4 text-muted-foreground/50" aria-hidden="true" />
                            <span className="sr-only">Not covered</span>
                          </>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Reveal>

      <Reveal className="mt-6">
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="text-[15px] font-medium">How a scan runs</h3>
          <p className="mt-1.5 text-sm text-muted-foreground">
            Each stage reports its own status. A stage that fails or gets skipped stays visible on the result —
            an empty findings list never silently means &ldquo;clean&rdquo;.
          </p>
          <ol className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {STAGE_ORDER.map((stage, index) => (
              <li key={stage} className="flex items-start gap-3">
                <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-border font-mono text-[11px] text-muted-foreground">
                  {index + 1}
                </span>
                <div>
                  <p className="text-[13px] font-medium text-foreground">{STAGE_LABELS[stage]}</p>
                  <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{STAGE_DETAIL[stage]}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </Reveal>
    </section>
  );
}
