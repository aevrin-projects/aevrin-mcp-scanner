import type { Finding, Severity } from "./types";

/** How much one finding of this severity moves the 0-100 scan score. */
export function scoreImpactForSeverity(severity: Severity) {
  if (severity === "critical") return "-40";
  if (severity === "high") return "-20";
  if (severity === "medium") return "-8";
  if (severity === "low") return "-3";
  return "No score impact";
}

export function summarizeFindings(findings: Finding[]): Record<Severity, number> {
  const counts: Record<Severity, number> = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
  for (const finding of findings) counts[finding.severity] += 1;
  return counts;
}
