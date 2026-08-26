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
  D: "border-severity-critical/40 bg-severity-critical/10 text-severity-critical",
};

export function TrustGradeBadge({
  grade,
  label,
  score,
  className,
}: {
  grade: TrustGrade;
  label: string;
  score?: number | null;
  className?: string;
}) {
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <span
        aria-hidden="true"
        className={cn(
          "inline-flex size-7 shrink-0 items-center justify-center rounded-md border text-sm font-semibold",
          GRADE_CLASSES[grade],
        )}
      >
        {grade}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium">
          <span className="sr-only">Grade {grade}: </span>
          {label}
        </span>
        {typeof score === "number" ? (
          <span className="block text-xs text-muted-foreground tabular-nums">{score}/100</span>
        ) : null}
      </span>
    </span>
  );
}
