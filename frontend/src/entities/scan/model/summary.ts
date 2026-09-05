import type { Severity } from "@/entities/finding";
import type { Scan, ScanStage } from "./types";

/** Stage tallies for the coverage strip: how much of the pipeline actually
 *  ran, rather than just whether the scan finished. */
export function summarizeCoverage(stages: ScanStage[]) {
  const by = (status: ScanStage["status"]) => stages.filter((stage) => stage.status === status).length;
  return {
    completed: by("done"),
    failed: by("failed"),
    skipped: by("skipped"),
    running: by("running"),
    queued: by("pending"),
  };
}

export function uniqueTargets(scans: Scan[]) {
  return new Set(scans.map((scan) => scan.target)).size;
}

export function verdictLabel(scan: Scan, activeCounts: Record<Severity, number>) {
  if (scan.status === "failed") return "Scan failed";
  // An ungraded scan is its own state, and it outranks the finding counts:
  // the point of withholding the letter is that the findings do not add up
  // to an assessment, so summarising them as one would undo that.
  if (scan.status === "incomplete" || scan.grade === null) return "Not graded";
  if (activeCounts.critical > 0) return "Critical issues need attention";
  if (activeCounts.high > 0) return "High-risk findings need review";
  if (scan.risk_score !== null && scan.risk_score <= 9) return "No significant issues found";
  if (scan.risk_score !== null && scan.risk_score <= 24) return "Lower-severity issues found";
  return "Review the findings before use";
}
