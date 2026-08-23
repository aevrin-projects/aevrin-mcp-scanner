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
  if (scan.status === "incomplete") return "Partial coverage";
  if (activeCounts.critical > 0) return "Critical issues need attention";
  if (activeCounts.high > 0) return "High-risk findings need review";
  if (scan.score !== null && scan.score >= 90) return "No significant issues in completed checks";
  if (scan.score !== null && scan.score >= 70) return "Lower-severity issues found";
  return "Review the findings before use";
}
