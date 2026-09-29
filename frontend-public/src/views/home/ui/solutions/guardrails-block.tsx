"use client";

import { useState } from "react";
import {
  Clock,
  Minus,
  Plus,
  ShieldCheck,
  ShieldX,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { BrandIcon } from "@/shared/ui/brand-icon";
import { SolutionBlock, type SeeAlsoLink } from "./solution-block";
import styles from "./solutions.module.css";
import { useSequence } from "./use-sequence";

/*
 * The hook's behaviour and every message line come from
 * `backend/cli/aevrin_cli/hook_script.py` (`_block_message`, the
 * `allow_unscanned` and `allow_clean` notes) and the decision table in
 * `controllers/hook_controller.py`. The posture view follows
 * `scanner-core/agents/posture.py` (named deductions, the band override for a
 * full shell that can reach credentials) and `agents/attack_paths.py` (the
 * path title, steps and remediation). The server, its URL, grades and the
 * finding ids are illustrative; `.example` is a reserved domain.
 */

type OutcomeKey = "clean" | "block" | "unscanned";

type Outcome = {
  key: OutcomeKey;
  label: string;
  node: string;
  icon: LucideIcon;
  description: string;
  decision: string;
  after: string;
};

const OUTCOMES: Outcome[] = [
  {
    key: "clean",
    label: "Allowed",
    node: "Allowed",
    icon: ShieldCheck,
    description:
      "The last scan left no unresolved high or critical findings. The install goes ahead, and your agent is told the grade and risk.",
    decision: "Allowed, clean scan on record",
    after: "The install continues",
  },
  {
    key: "block",
    label: "Denied with findings",
    node: "Denied",
    icon: ShieldX,
    description:
      "Unresolved high or critical findings stop the install. Your agent gets up to five of them, with their fixes and finding ids, and three options to put to you.",
    decision: "Denied with findings",
    after: "Your agent asks you what to do",
  },
  {
    key: "unscanned",
    label: "Allowed, scan queued",
    node: "Scan queued",
    icon: Clock,
    description:
      "Nothing is on record for this server yet. The install is allowed with a note, and a background scan starts, using one of your monthly hook scans.",
    decision: "Not yet scanned, allowed",
    after: "The scan is cached for next time",
  },
];

const SCHEDULE: readonly number[] = [150, 700, 1300, 1900];
const TARGET = "https://docs-mcp.acme.example/mcp";

const SEE_ALSO: SeeAlsoLink[] = [
  { label: "Set up the Claude Code hook", href: "https://docs.mcp.aevrin.net/hook" },
  { label: "How agent posture is scored", href: "https://docs.mcp.aevrin.net/agent-posture" },
];

function Wire({ lit }: { lit: boolean }) {
  return (
    <span className="relative mx-auto block h-7 w-px" style={{ background: "var(--mk-line-strong)" }}>
      <span className={cn(styles.wire, "absolute inset-0")} style={{ background: "var(--mk-fg)" }} data-on={lit} />
    </span>
  );
}

const BRANCHES: Record<OutcomeKey, string> = {
  clean: "M150 0 V10 C150 30 50 22 50 42 V52",
  block: "M150 0 V52",
  unscanned: "M150 0 V10 C150 30 250 22 250 42 V52",
};

function HookMessage({ outcome }: { outcome: OutcomeKey }) {
  if (outcome === "clean") {
    return (
      <p className={cn(styles.mono, "text-xs leading-[18px]")} style={{ color: "var(--mk-fg)" }}>
        Aevrin: clean scan on record (grade A, risk 4/100).
      </p>
    );
  }
  if (outcome === "unscanned") {
    return (
      <p className={cn(styles.mono, "text-xs leading-[18px]")} style={{ color: "var(--mk-fg)" }}>
        Aevrin: this target has not been scanned yet. Allowing for now; a background scan has been
        started and will be cached for next time.
      </p>
    );
  }
  return (
    <div className="space-y-2.5">
      <p className={cn(styles.mono, "text-xs leading-[18px]")} style={{ color: "var(--mk-fg)" }}>
        Aevrin: this MCP server has grade D, risk 62/100, with unresolved high/critical findings:
      </p>
      <ul className="space-y-1.5">
        {[
          { title: "Arbitrary Code Execution", owasp: "MCP05" },
          { title: "Secret Handling", owasp: "MCP01" },
        ].map((f) => (
          <li key={f.title} className="flex items-center gap-2 text-xs">
            <span className={styles.chip}>
              <span className={styles.sev} data-sev="high" aria-hidden="true" />
              High
            </span>
            <span className="min-w-0 truncate" style={{ color: "var(--mk-fg)" }}>
              {f.title}
            </span>
            <span className={cn(styles.mono, styles.dim)}>{f.owasp}</span>
          </li>
        ))}
      </ul>
      <p className={cn(styles.dim, "text-xs")}>You have 3 options. Ask the person which they want:</p>
      <ol className="space-y-1.5 text-xs leading-[18px]" style={{ color: "var(--mk-fg)" }}>
        <li className="flex gap-2">
          <span className={cn(styles.mono, styles.dim)}>1</span>
          <span>Fix it, then retry the install.</span>
        </li>
        <li className="flex min-w-0 gap-2">
          <span className={cn(styles.mono, styles.dim)}>2</span>
          <span className="min-w-0">
            Install anyway:{" "}
            <code className={cn(styles.mono, "break-all")}>aevrin hook allow {TARGET}</code>
          </span>
        </li>
        <li className="flex min-w-0 gap-2">
          <span className={cn(styles.mono, styles.dim)}>3</span>
          <span className="min-w-0">
            False report:{" "}
            <code className={cn(styles.mono, "break-all")}>
              aevrin findings triage &lt;finding id&gt; false_positive
            </code>
          </span>
        </li>
      </ol>
    </div>
  );
}

function HookView({ outcome, step }: { outcome: OutcomeKey; step: number }) {
  const current = OUTCOMES.find((o) => o.key === outcome) ?? OUTCOMES[1];
  const steps = ["Install attempted", "Last scan checked", current.decision, current.after];
  const shown = Math.max(step, 1);

  return (
    <div className="flex flex-col items-center">
      <div
        className={cn(styles.node, "flex h-9 max-w-full items-center gap-2 rounded-full border px-3.5")}
        style={{ background: "var(--mk-surface)", borderColor: "var(--mk-line-strong)" }}
        data-lit={step >= 1 && step < 3 ? "true" : "idle"}
      >
        <BrandIcon name="claude" className="size-4" />
        <span className="shrink-0 text-[13px] font-medium" style={{ color: "var(--mk-fg)" }}>
          Claude Code
        </span>
        <span className={cn(styles.mono, styles.dim, "min-w-0 truncate text-xs")}>
          claude mcp add --transport http acme-docs {TARGET}
        </span>
      </div>

      <Wire lit={step >= 2} />

      <div className="relative flex items-center">
        <span
          className={cn(styles.node, "flex size-14 items-center justify-center rounded-full border")}
          style={{ background: "var(--mk-surface)", borderColor: "var(--mk-line-strong)", color: "var(--mk-fg)" }}
          data-lit={step >= 2 && step < 4 ? "true" : "idle"}
        >
          <ShieldCheck className="size-5" />
        </span>
        <span className="absolute left-full ml-3 w-max text-left">
          <span className="block text-[13px] font-medium" style={{ color: "var(--mk-fg)" }}>
            Aevrin hook
          </span>
          <span className={cn(styles.dim, "block text-xs")}>Last scan checked</span>
        </span>
      </div>

      <div className="w-full max-w-[360px]">
        <svg viewBox="0 0 300 52" preserveAspectRatio="none" className="block h-[52px] w-full" fill="none">
          {OUTCOMES.map((o) => (
            <path
              key={o.key}
              d={BRANCHES[o.key]}
              stroke="var(--mk-line-strong)"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          <path
            d={BRANCHES[outcome]}
            stroke="var(--mk-fg)"
            strokeWidth="1.5"
            vectorEffect="non-scaling-stroke"
            className={styles.branchLit}
            style={{ opacity: step >= 3 ? 1 : 0 }}
          />
        </svg>
        <div className="grid grid-cols-3">
          {OUTCOMES.map((o) => {
            const Icon = o.icon;
            const lit = step >= 3 ? (o.key === outcome ? "true" : "false") : "idle";
            return (
              <div key={o.key} className="flex flex-col items-center gap-1.5">
                <span
                  className={cn(styles.node, "flex size-11 items-center justify-center rounded-full border")}
                  style={{ background: "var(--mk-surface)", borderColor: "var(--mk-line-strong)", color: "var(--mk-fg)" }}
                  data-lit={lit}
                >
                  <Icon
                    className={cn(
                      "size-4",
                      o.key === "block" ? styles.bad : o.key === "clean" ? styles.ok : styles.warn,
                    )}
                  />
                </span>
                <span className="text-center text-xs" style={{ color: "var(--mk-fg)" }}>
                  {o.node}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-5 w-full">
        <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 px-1">
          <span className="flex gap-1">
            {steps.map((label, index) => (
              <span
                key={label}
                className={cn(styles.fade, "h-1 w-4 rounded-full")}
                style={{ background: index < shown ? "var(--mk-fg)" : "var(--mk-line-strong)" }}
              />
            ))}
          </span>
          <span className={cn(styles.dim, "text-xs whitespace-nowrap")}>
            Step {shown} of 4
          </span>
          <span className="min-w-0 basis-full text-xs font-medium @min-[440px]:basis-auto" style={{ color: "var(--mk-fg)" }}>
            {steps[shown - 1]}
          </span>
        </div>
        <div className={cn(styles.panel, styles.step, "p-3.5")} data-on={step >= 4}>
          <p className={cn(styles.dim, "mb-2 text-xs")}>What your agent is told</p>
          <HookMessage outcome={outcome} />
        </div>
      </div>
    </div>
  );
}

function PostureView() {
  const factors = [
    { points: 15, reason: "unrestricted shell access" },
    { points: 15, reason: "3 MCP server(s) approved without a prompt" },
    { points: 15, reason: "credentials reachable from a shell this agent can use: github_token" },
  ];
  const path = [
    { label: "Shell", detail: "runs any command" },
    { label: "gh", detail: "reads the credential without being given it" },
    { label: "github token", detail: "present at GITHUB_TOKEN" },
  ];

  return (
    <div className={cn(styles.swap, "space-y-3")}>
      <section aria-label="Agent posture" className={cn(styles.panel, "p-4")}>
        <div className="flex flex-wrap items-center gap-2">
          <BrandIcon name="claude" className="size-4" />
          <span className="text-[13px] font-medium" style={{ color: "var(--mk-fg)" }}>
            Claude Code
          </span>
          <span className="ml-auto flex items-center gap-2">
            <span className="text-xs tabular-nums" style={{ color: "var(--mk-fg)" }}>
              Posture 55/100
            </span>
            <span className={styles.chip}>
              <span className={styles.sev} data-sev="critical" aria-hidden="true" />
              Critical
            </span>
          </span>
        </div>
        <ul className="mt-3 space-y-1.5">
          {factors.map((f) => (
            <li key={f.reason} className="flex gap-2.5 text-xs leading-[18px]">
              <span className={cn(styles.mono, "w-7 shrink-0 tabular-nums")} style={{ color: "var(--mk-fg)" }}>
                -{f.points}
              </span>
              <span className={styles.dim}>{f.reason}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 border-t pt-2.5 text-xs leading-[18px]" style={{ borderColor: "var(--mk-line)", color: "var(--mk-fg)" }}>
          Critical rather than high: a full shell that can reach credentials outranks the score.
        </p>
      </section>

      <section aria-label="Attack path" className={cn(styles.panel, "relative z-10 ml-4 p-4")}>
        <div className="flex flex-wrap items-center gap-2">
          <TriangleAlert className={cn(styles.bad, "size-3.5")} aria-hidden="true" />
          <span className="text-[13px] font-medium" style={{ color: "var(--mk-fg)" }}>
            Shell access reaches every repository this token can reach
          </span>
        </div>
        <ol className="mt-3 flex flex-wrap items-stretch gap-1.5">
          {path.map((p, index) => (
            <li key={p.label} className="flex items-center gap-1.5">
              <span className={cn(styles.inset, "px-2 py-1.5")}>
                <span className={cn(styles.mono, "block text-xs font-medium")} style={{ color: "var(--mk-fg)" }}>
                  {p.label}
                </span>
                <span className={cn(styles.dim, "block text-xs")}>{p.detail}</span>
              </span>
              {index < path.length - 1 ? (
                <span className={styles.dim} aria-hidden="true">
                  &rarr;
                </span>
              ) : null}
            </li>
          ))}
        </ol>
        <p className={cn(styles.dim, "mt-3 text-xs leading-[18px]")}>
          Fix: narrow the shell permission so <code className={styles.mono}>gh</code> is not runnable,
          or move the credential out of this machine&apos;s environment and file system.
        </p>
      </section>

      <p className={cn(styles.dim, "px-1 text-xs leading-[18px]")}>
        Read from <code className={styles.mono}>settings.json</code> and{" "}
        <code className={styles.mono}>.mcp.json</code>. Nothing is executed, and the report stays on
        your machine unless you pass <code className={styles.mono}>--upload</code>.
      </p>
    </div>
  );
}

export function GuardrailsBlock() {
  const [outcome, setOutcome] = useState<OutcomeKey>("block");
  const [view, setView] = useState<"hook" | "posture">("hook");
  const { ref, step, replay } = useSequence<HTMLElement>(SCHEDULE);

  const choose = (key: OutcomeKey) => {
    setOutcome(key);
    setView("hook");
    replay();
  };

  const aside = (
    <div role="group" aria-label="Hook outcomes" className="border-t" style={{ borderColor: "var(--mk-line)" }}>
      {OUTCOMES.map((o) => {
        const selected = view === "hook" && outcome === o.key;
        const Icon = o.icon;
        return (
          <div key={o.key} className="border-b" style={{ borderColor: "var(--mk-line)" }}>
            <button
              type="button"
              aria-pressed={selected}
              onClick={() => choose(o.key)}
              className={cn(
                styles.focusRing,
                "flex w-full items-center gap-3 rounded-md py-3.5 text-left text-base font-medium",
              )}
              style={{ color: "var(--mk-fg)" }}
            >
              <Icon
                className={cn("size-4 shrink-0", o.key === "block" ? styles.bad : o.key === "clean" ? styles.ok : styles.warn)}
                aria-hidden="true"
              />
              <span className="flex-1">{o.label}</span>
              {selected ? (
                <Minus className={cn(styles.dim, "size-4")} aria-hidden="true" />
              ) : (
                <Plus className={cn(styles.dim, "size-4")} aria-hidden="true" />
              )}
            </button>
            {selected ? (
              <p className={cn(styles.swap, "pb-4 pl-7 text-[15px] leading-6")} style={{ color: "var(--mk-muted)" }}>
                {o.description}
              </p>
            ) : null}
          </div>
        );
      })}
    </div>
  );

  const mockup = (
    <figure ref={ref} aria-labelledby="sb-guard-caption" className={cn(styles.tile, "@container")}>
      <figcaption id="sb-guard-caption" className="sr-only">
        Illustrative example: the Aevrin hook checking an MCP server install in Claude Code, and an
        agent posture report. The server and figures are fictional.
      </figcaption>
      <div className="flex flex-col p-3 @min-[440px]:min-h-[600px] @min-[440px]:p-6">
        <div
          role="group"
          aria-label="Mockup view"
          className="flex w-fit gap-1 rounded-lg border p-1"
          style={{ borderColor: "var(--mk-line)", background: "var(--sb-chip)" }}
        >
          {(
            [
              ["hook", "Install check"],
              ["posture", "Agent posture"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              aria-pressed={view === key}
              onClick={() => setView(key)}
              className={cn(styles.segment, styles.focusRing, "h-7 rounded-md px-3 text-xs font-medium")}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="mt-6 flex-1">
          {view === "hook" ? (
            <div className={styles.swap}>
              <HookView outcome={outcome} step={step} />
            </div>
          ) : (
            <PostureView />
          )}
        </div>
        <p className={cn(styles.dim, "mt-5 px-1 text-xs leading-[18px]")}>
          If Aevrin is unreachable, or the check times out, the hook allows the install without a
          word.
        </p>
      </div>
    </figure>
  );

  return (
    <SolutionBlock
      id="solution-guardrails"
      eyebrow="03  AGENT GUARDRAILS"
      title="Guardrails for the agents you already run"
      body={
        <p>
          When Claude Code runs <code className={styles.mono}>claude mcp add</code> or writes{" "}
          <code className={styles.mono}>.mcp.json</code>, Aevrin&apos;s PreToolUse hook checks that
          server&apos;s last scan. Unresolved high or critical findings stop the install, and your
          agent gets the findings and three options: fix it, install anyway, or dispute a finding. A
          server not yet scanned is allowed with a note while a scan runs. If Aevrin is unreachable,
          the hook stays out of the way.
        </p>
      }
      aside={aside}
      seeAlso={SEE_ALSO}
      mockup={mockup}
    />
  );
}
