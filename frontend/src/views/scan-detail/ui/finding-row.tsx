"use client";

import Link from "next/link";
import { ChevronRight, Sparkles } from "lucide-react";
import type { Finding, Severity } from "@/entities/finding";
import { OWASP_CATEGORY_LABELS } from "@/entities/finding";

/**
 * One finding, as a row you can skim.
 *
 * These were table cells, which meant the title competed with the tool name
 * and the OWASP category for the same visual weight, and the severity was a
 * badge in a column you had to look for. A severity rail puts it where the
 * eye already is, and everything that is context rather than the finding
 * itself drops to one quiet line.
 */

const RAIL: Record<Severity, string> = {
  critical: "bg-severity-critical-solid",
  high: "bg-severity-high",
  medium: "bg-severity-medium",
  low: "bg-severity-low",
  info: "bg-border",
};

const SEVERITY_TEXT: Record<Severity, string> = {
  critical: "text-severity-critical",
  high: "text-severity-high",
  medium: "text-severity-medium",
  low: "text-severity-low",
  info: "text-muted-foreground",
};

export function FindingRow({ finding, href }: { finding: Finding; href: string }) {
  const resolved = finding.triage_status !== "open";
  const location = finding.file_path
    ? `${finding.file_path}${finding.line_start ? `:${finding.line_start}` : ""}`
    : null;

  return (
    <Link
      href={href}
      className="group flex items-stretch gap-4 rounded-lg border border-transparent px-3 py-3.5 transition-colors hover:border-border hover:bg-card"
    >
      <span className={`w-0.5 shrink-0 rounded-full ${RAIL[finding.severity]}`} aria-hidden="true" />

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
          <span className={`text-[11px] font-medium uppercase tracking-[0.1em] ${SEVERITY_TEXT[finding.severity]}`}>
            {finding.severity}
          </span>
          <span className={`text-sm font-medium ${resolved ? "text-muted-foreground line-through" : ""}`}>
            {finding.title}
          </span>
          {/* A finding somebody has already judged should not read as
              outstanding work. */}
          {resolved ? (
            <span className="rounded-full border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground">
              {finding.triage_status === "fixed" ? "Fixed" : "False positive"}
            </span>
          ) : null}
          {finding.in_kev ? (
            <span className="rounded-full bg-severity-critical-solid px-1.5 py-0.5 text-[11px] font-medium text-severity-critical-foreground">
              Known exploited
            </span>
          ) : null}
        </div>

        {finding.description ? (
          <p className="mt-1.5 line-clamp-2 max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
            {finding.description}
          </p>
        ) : null}

        <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] text-muted-foreground">
          <span>{finding.tool}</span>
          <span aria-hidden="true">·</span>
          <span>{OWASP_CATEGORY_LABELS[finding.owasp_category] ?? finding.owasp_category}</span>
          {location ? (
            <>
              <span aria-hidden="true">·</span>
              <span className="truncate font-mono">{location}</span>
            </>
          ) : location === null && finding.manifest_field ? (
            <>
              <span aria-hidden="true">·</span>
              <span className="truncate font-mono">{finding.manifest_field}</span>
            </>
          ) : null}
          {finding.epss_score !== null ? (
            <>
              <span aria-hidden="true">·</span>
              <span>
                EPSS {(finding.epss_score * 100).toFixed(finding.epss_score < 0.01 ? 2 : 0)}%
              </span>
            </>
          ) : null}
          {finding.occurrence_count > 1 ? (
            <>
              <span aria-hidden="true">·</span>
              <span>{finding.occurrence_count} occurrences</span>
            </>
          ) : null}
        </p>

        {/* Only when the AI disagreed with the scanner. "AI agrees" on every
            row would be noise on the one screen that has to stay scannable. */}
        {finding.llm_classification === "likely_false_positive" ? (
          <p className="mt-1.5 flex items-center gap-1.5 text-[12px] text-chart-1">
            <Sparkles className="size-3" aria-hidden="true" />
            AI review: likely a false positive
          </p>
        ) : finding.llm_severity && finding.llm_severity !== finding.severity ? (
          <p className="mt-1.5 flex items-center gap-1.5 text-[12px] text-muted-foreground">
            <Sparkles className="size-3" aria-hidden="true" />
            AI review suggests {finding.llm_severity}
          </p>
        ) : null}
      </div>

      <ChevronRight
        className="mt-0.5 size-4 shrink-0 self-center text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
        aria-hidden="true"
      />
    </Link>
  );
}
