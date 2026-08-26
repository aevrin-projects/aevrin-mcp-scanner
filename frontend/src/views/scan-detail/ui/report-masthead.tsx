"use client";

import { AlertTriangle, ShieldCheck, ShieldX } from "lucide-react";
import type { Severity } from "@/entities/finding";
import type { Scan, ScanStage } from "@/entities/scan";
import { STAGE_LABELS, STAGE_ORDER } from "@/entities/scan";
import { TARGET_TYPE_LABELS, verdictLabel } from "@/entities/scan";
import { formatDateTime } from "@/shared/lib/format";

/**
 * The top of a scan report.
 *
 * The page used to open with a row of equal-weight cards, so the score, the
 * target and the finding count all arrived at once with nothing to read
 * first. A report has an answer, and the answer should be the largest thing
 * on the page -- then the shape of the problem, then the evidence.
 */

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
  info: "Info",
};

// Solid fills for the distribution bar. Severity hues are only ever used
// beside a written severity, never as the sole carrier of meaning.
const SEVERITY_FILL: Record<Severity, string> = {
  critical: "bg-severity-critical-solid",
  high: "bg-severity-high",
  medium: "bg-severity-medium",
  low: "bg-severity-low",
  info: "bg-muted-foreground/50",
};

const SEVERITY_TEXT: Record<Severity, string> = {
  critical: "text-severity-critical",
  high: "text-severity-high",
  medium: "text-severity-medium",
  low: "text-severity-low",
  info: "text-muted-foreground",
};

function scoreTone(scan: Scan) {
  // Never a reassuring colour on a scan that did not finish. A 100 in green
  // is the most comforting thing this page can show, and an incomplete scan
  // is the least reliable result it can produce.
  if (scan.status === "incomplete" || scan.status === "failed") return "text-severity-high";
  if (scan.score === null) return "text-muted-foreground";
  if (scan.score >= 90) return "text-chart-1";
  if (scan.score >= 70) return "text-severity-medium";
  return "text-severity-critical";
}

function SeverityBar({ counts, total }: { counts: Record<Severity, number>; total: number }) {
  if (total === 0) return null;
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-muted">
      {SEVERITY_ORDER.filter((s) => counts[s] > 0).map((severity) => (
        <div
          key={severity}
          className={SEVERITY_FILL[severity]}
          style={{ width: `${(counts[severity] / total) * 100}%` }}
          // The counts are written out beneath, so this is decoration.
          aria-hidden="true"
        />
      ))}
    </div>
  );
}

export function ReportMasthead({
  scan,
  stages,
  counts,
  openCount,
}: {
  scan: Scan;
  stages: ScanStage[];
  counts: Record<Severity, number>;
  openCount: number;
}) {
  const total = SEVERITY_ORDER.reduce((sum, s) => sum + counts[s], 0);
  const verdict = verdictLabel(scan, counts);
  const settled = scan.status === "completed" || scan.status === "incomplete";
  const trustworthy = scan.status === "completed";

  const notRun = STAGE_ORDER.filter((name) => {
    const stage = stages.find((s) => s.name === name);
    return stage && (stage.status === "failed" || stage.status === "skipped");
  });

  const Icon = !trustworthy ? AlertTriangle : total === 0 ? ShieldCheck : ShieldX;

  return (
    <section className="border-b border-border pb-8">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[13px] text-muted-foreground">
        <span className="uppercase tracking-[0.14em]">{TARGET_TYPE_LABELS[scan.target_type]}</span>
        <span aria-hidden="true">·</span>
        <span className="font-mono break-all text-foreground">{scan.target}</span>
      </div>

      <div className="mt-6 flex flex-wrap items-end justify-between gap-x-10 gap-y-6">
        <div className="min-w-0 max-w-2xl">
          {/* The verdict in the display face the rest of the product uses for
              things it means. A sentence, not a status chip. */}
          <h1 className="font-display text-4xl leading-[1.1] tracking-tight sm:text-5xl">
            {verdict}
          </h1>
          <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
            <Icon className={`size-4 shrink-0 ${trustworthy ? "" : "text-severity-high"}`} aria-hidden="true" />
            {trustworthy
              ? `${openCount} open finding${openCount === 1 ? "" : "s"} across every check that ran.`
              : "Some checks did not run, so this is inconclusive rather than clean."}
          </p>
        </div>

        {settled && scan.score !== null ? (
          <div className="shrink-0">
            <div className="flex items-baseline gap-1.5">
              <span className={`font-display text-6xl leading-none tabular-nums ${scoreTone(scan)}`}>
                {scan.score}
              </span>
              <span className="font-display text-2xl leading-none text-muted-foreground">/100</span>
            </div>
            <p className="mt-1.5 text-right text-[13px] text-muted-foreground">
              {formatDateTime(scan.completed_at ?? scan.created_at)}
            </p>
          </div>
        ) : null}
      </div>

      {total > 0 ? (
        <div className="mt-8">
          <SeverityBar counts={counts} total={total} />
          <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1.5">
            {SEVERITY_ORDER.filter((s) => counts[s] > 0).map((severity) => (
              <div key={severity} className="flex items-baseline gap-1.5">
                <dt className={`text-[13px] ${SEVERITY_TEXT[severity]}`}>{SEVERITY_LABEL[severity]}</dt>
                <dd className="text-[13px] tabular-nums text-muted-foreground">{counts[severity]}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}

      {/* What did not run, said plainly and in place, rather than as one more
          alert box competing with the others. This is the product's central
          claim: a check that did not run is not a check that passed. */}
      {notRun.length > 0 ? (
        <div className="mt-8 border-l-2 border-severity-high pl-4">
          <p className="text-[13px] font-medium text-severity-high">
            {notRun.map((n) => STAGE_LABELS[n]).join(", ")} did not run
          </p>
          <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
            Usually Docker not running, a missing binary, or no network. Nothing below reflects
            those checks, so treat the result as inconclusive rather than clean.
          </p>
        </div>
      ) : null}
    </section>
  );
}
