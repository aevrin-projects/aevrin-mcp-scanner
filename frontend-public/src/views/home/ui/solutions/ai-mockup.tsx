"use client";

import { useState } from "react";
import { Check, CircleDashed, KeyRound, ShieldCheck, Sparkles } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import styles from "./solutions.module.css";
import { PROVIDERS, ProviderMark, type ProviderKey } from "./provider-mark";
import { useSequence } from "./use-sequence";

/*
 * Sources for what this shows:
 * - Explanation panel: `frontend/src/features/ai-explain/ui/explain-button.tsx`
 *   ("AI explanation", provider attribution, "Explain more", and its closing
 *   line, quoted verbatim). No model id is shown: the model is whichever one
 *   the key's owner picked from the provider's live catalogue.
 * - AI review labels: `backend/api/aevrin_api/services/triage.py`
 *   (confirmed / likely_false_positive / needs_review, one-sentence reason).
 * - Triage states: `aevrin findings triage` (open / fixed / false_positive).
 * - Rule titles and OWASP codes: `scanner-core/mcp/catalog.py`.
 * The server, tool name and findings are illustrative.
 */

type Sev = "high" | "medium" | "low" | "info";
type State = "open" | "fixed" | "false positive";

const FINDINGS: { title: string; owasp: string; sev: Sev; state: State; flipsAt: number }[] = [
  { title: "Secret Handling", owasp: "MCP01", sev: "high", state: "open", flipsAt: 0 },
  { title: "Arbitrary Code Execution", owasp: "MCP05", sev: "high", state: "fixed", flipsAt: 1 },
  { title: "Excessive Permissions", owasp: "MCP09", sev: "medium", state: "fixed", flipsAt: 2 },
  { title: "Tool Poisoning", owasp: "MCP02", sev: "medium", state: "false positive", flipsAt: 3 },
  { title: "Missing Rate-Limit or Timeout", owasp: "MCP09", sev: "low", state: "fixed", flipsAt: 4 },
  { title: "Insufficient Tool Metadata", owasp: "MCP02", sev: "info", state: "open", flipsAt: 0 },
];
const TOTAL = FINDINGS.length;

const SCHEDULE: readonly number[] = [600, 1100, 1600, 2100];

const REVIEW_LABELS = ["Confirmed", "Likely false positive", "Needs review"] as const;

function StateChip({ state }: { state: State }) {
  const Icon = state === "open" ? CircleDashed : Check;
  return (
    <span className={cn(styles.chip, styles.swap, "shrink-0")} key={state}>
      <Icon className={cn("size-3", state === "open" ? styles.dim : styles.ok)} aria-hidden="true" />
      {state}
    </span>
  );
}

export function AiMockup() {
  const { ref, step } = useSequence<HTMLElement>(SCHEDULE);
  const [provider, setProvider] = useState<ProviderKey>("anthropic");
  const [expanded, setExpanded] = useState(false);
  const providerLabel = PROVIDERS.find((p) => p.key === provider)?.label ?? "";

  const stateOf = (f: (typeof FINDINGS)[number]): State =>
    f.flipsAt > 0 && step >= f.flipsAt ? f.state : f.flipsAt > 0 ? "open" : f.state;
  const triaged = FINDINGS.filter((f) => stateOf(f) !== "open").length;

  return (
    <figure ref={ref} aria-labelledby="sb-ai-caption" className={cn(styles.tile, "@container")}>
      <figcaption id="sb-ai-caption" className="sr-only">
        Illustrative example of AI explanations and triage on a scan result. The server and
        findings are fictional.
      </figcaption>
      <div className="grid gap-3 p-3 @min-[440px]:p-5 @min-[560px]:grid-cols-[minmax(0,1.12fr)_minmax(0,1fr)] @min-[560px]:gap-0">
        {/* Left: the explanation, and the AI review layered over its foot. */}
        <div className="flex min-w-0 flex-col">
          <section aria-label="AI explanation" className={cn(styles.panel, "p-4 @min-[560px]:pr-8")}>
            <div className="flex items-center gap-2">
              <span className={cn(styles.dim, "inline-flex items-center gap-1.5 text-xs font-medium")}>
                <Sparkles className="size-3.5" aria-hidden="true" />
                AI explanation
              </span>
            </div>
            <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] font-medium" style={{ color: "var(--mk-fg)" }}>
              <span className="inline-flex items-center gap-1.5">
                <span className={styles.sev} data-sev="high" aria-hidden="true" />
                High
              </span>
              <span className={styles.dim} aria-hidden="true">·</span>
              <span>Secret Handling</span>
              <span className={cn(styles.mono, styles.dim, "text-xs font-normal")}>MCP01</span>
            </p>
            <p className="mt-2 text-[13px] leading-5" style={{ color: "var(--mk-fg)" }}>
              The <span className={styles.mono}>run_query</span> tool asks for the database password
              as an argument. Whatever the agent passes lands in the conversation, and from there in
              transcripts and logs.
            </p>
            {expanded ? (
              <p id="sb-ai-detail" className={cn(styles.dim, styles.swap, "mt-2 text-[13px] leading-5")}>
                Read the password from the server&apos;s own environment instead of accepting it as
                tool input, then confirm nothing logs the argument. The scan set this finding and its
                severity; this text does not change either.
              </p>
            ) : null}
            <div className="mt-3">
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                aria-expanded={expanded}
                aria-controls={expanded ? "sb-ai-detail" : undefined}
                className={cn(
                  styles.focusRing,
                  "h-7 rounded-md border px-2.5 text-xs font-medium transition-colors hover:bg-[var(--mk-hover)]",
                )}
                style={{ borderColor: "var(--mk-line)", color: "var(--mk-fg)" }}
              >
                {expanded ? "Show less" : "Explain more"}
              </button>
            </div>
            <div className="mt-3 border-t pt-2.5" style={{ borderColor: "var(--mk-line)" }}>
              <p className="text-xs" style={{ color: "var(--mk-fg)" }} aria-live="polite">
                <span key={provider} className={cn(styles.swap, "inline-flex items-start gap-1.5")}>
                  <ProviderMark provider={provider} className="mt-px size-3.5" />
                  <span>
                    <span className="block whitespace-nowrap">Explained by {providerLabel}</span>
                    <span className={cn(styles.dim, "block")}>with the model you chose</span>
                  </span>
                </span>
              </p>
              <p className={cn(styles.dim, "mt-1.5 text-xs leading-[18px]")}>
                Generated from Aevrin&apos;s scan evidence. It explains findings; it does not produce
                them, and it cannot change a score or a grade.
              </p>
            </div>
          </section>

          <section
            aria-label="AI review"
            className={cn(styles.panel, "relative z-10 -mt-3 ml-4 p-4 @min-[560px]:ml-7 @min-[560px]:mr-3")}
          >
            <div className="flex items-center gap-2">
              <ShieldCheck className="size-3.5" style={{ color: "var(--mk-fg)" }} aria-hidden="true" />
              <span className="text-[13px] font-medium" style={{ color: "var(--mk-fg)" }}>
                AI review
              </span>
              <span className={cn(styles.dim, "ml-auto text-xs")}>Secret Handling</span>
            </div>
            <ul className="mt-2.5 flex flex-wrap gap-1.5" aria-label="Review label">
              {REVIEW_LABELS.map((label) => {
                const chosen = label === "Confirmed";
                return (
                  <li
                    key={label}
                    className={cn(styles.chip, !chosen && styles.dim)}
                    style={chosen ? { borderColor: "var(--mk-fg)", color: "var(--mk-fg)" } : undefined}
                  >
                    {chosen ? <Check className={cn(styles.ok, "size-3")} aria-hidden="true" /> : null}
                    {label}
                    {chosen ? <span className="sr-only"> (this finding)</span> : null}
                  </li>
                );
              })}
            </ul>
            <p className="mt-2.5 text-[13px] leading-5" style={{ color: "var(--mk-fg)" }}>
              A real credential passes through a tool argument, so the finding stands.
            </p>
          </section>
        </div>

        {/* Right: triage progress, and the provider picker. */}
        <div className="relative z-20 flex min-w-0 flex-col gap-3 @min-[560px]:-ml-4 @min-[560px]:mt-9">
          <section aria-label="Triage" className={cn(styles.panel, "p-4")}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[13px] font-medium" style={{ color: "var(--mk-fg)" }}>
                Findings
              </span>
              <span className="text-xs tabular-nums" style={{ color: "var(--mk-fg)" }}>
                {triaged} of {TOTAL} triaged
              </span>
            </div>
            <div
              className="mt-2 h-1 overflow-hidden rounded-full"
              style={{ background: "var(--sb-chip)" }}
              role="progressbar"
              aria-label="Findings triaged"
              aria-valuemin={0}
              aria-valuemax={TOTAL}
              aria-valuenow={triaged}
            >
              <div
                className={cn(styles.bar, "h-full rounded-full")}
                style={{ background: "var(--mk-fg)", transform: `scaleX(${triaged / TOTAL})` }}
              />
            </div>
            <ul className="mt-3 space-y-2">
              {FINDINGS.map((f) => {
                const state = stateOf(f);
                return (
                  <li key={f.title} className="flex gap-2">
                    <span className={cn(styles.sev, "mt-[7px]")} data-sev={f.sev} aria-hidden="true" />
                    <span className="min-w-0 flex-1">
                      <span
                        className={cn(
                          "block truncate text-[13px] leading-5",
                          state !== "open" && "line-through decoration-[var(--mk-muted)]",
                        )}
                        style={{ color: "var(--mk-fg)" }}
                      >
                        {f.title}
                      </span>
                      <span className={cn(styles.dim, "mt-0.5 flex items-center justify-between gap-2 text-xs")}>
                        <span>
                          <span className={styles.mono}>{f.owasp}</span> · {f.sev}
                        </span>
                        <StateChip state={state} />
                      </span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>

          <section aria-label="Provider for explanations" className={cn(styles.panel, "p-3")}>
            <p className={cn(styles.dim, "px-1 text-xs")}>Explain with your own key</p>
            <div role="group" aria-label="AI provider" className="mt-2 grid grid-cols-2 gap-1.5 @min-[440px]:grid-cols-4 @min-[560px]:grid-cols-2">
              {PROVIDERS.map((p) => (
                <button
                  key={p.key}
                  type="button"
                  aria-pressed={provider === p.key}
                  onClick={() => setProvider(p.key)}
                  className={cn(
                    styles.provider,
                    styles.focusRing,
                    "flex min-w-0 flex-col items-start gap-1.5 rounded-lg border p-2 text-left",
                  )}
                  style={{ borderColor: provider === p.key ? undefined : "var(--mk-line)" }}
                >
                  <span className="flex w-full min-w-0 items-center gap-1.5">
                    <ProviderMark provider={p.key} className="size-3.5" />
                    <span className="text-xs leading-4 font-medium" style={{ color: "var(--mk-fg)" }}>
                      {p.label}
                    </span>
                  </span>
                  <span className={cn(styles.dim, "inline-flex items-center gap-1 text-xs")}>
                    <KeyRound className="size-3" aria-hidden="true" />
                    Your key
                  </span>
                </button>
              ))}
            </div>
          </section>
        </div>
      </div>
    </figure>
  );
}
