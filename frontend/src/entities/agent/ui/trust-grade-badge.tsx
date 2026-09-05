import { cn } from "@/shared/lib/utils";
import type { TrustGrade } from "../model/types";

/**
 * Letter and word together, never the letter alone and never colour alone.
 * A grade has to survive being read in greyscale, at a glance, by someone who
 * has never seen this scale before.
 */
const GRADE_CLASSES: Record<TrustGrade, string> = {
  A: "border-brand/40 bg-brand/10 text-brand-text",
  B: "border-border bg-muted text-foreground",
  C: "border-severity-medium/40 bg-severity-medium/10 text-severity-medium",
  D: "border-severity-high/40 bg-severity-high/10 text-severity-high",
  F: "border-severity-critical/40 bg-severity-critical/10 text-severity-critical",
};

// A scan that could not be graded gets no letter and no colour. "?" reads as
// "we could not tell", which is exactly right and is not a verdict.
const UNGRADED_CLASS = "border-border bg-muted text-muted-foreground";

export function TrustGradeBadge({
  grade,
  label,
  riskScore,
  className,
}: {
  grade: TrustGrade | null;
  label: string;
  riskScore?: number | null;
  className?: string;
}) {
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <span
        aria-hidden="true"
        className={cn(
          "inline-flex size-7 shrink-0 items-center justify-center rounded-md border text-sm font-semibold",
          grade ? GRADE_CLASSES[grade] : UNGRADED_CLASS,
        )}
      >
        {grade ?? "?"}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium">
          <span className="sr-only">{grade ? `Grade ${grade}: ` : "Not graded: "}</span>
          {label}
        </span>
        {typeof riskScore === "number" ? (
          <span className="block text-xs text-muted-foreground tabular-nums">
            risk {riskScore}/100
          </span>
        ) : null}
      </span>
    </span>
  );
}
