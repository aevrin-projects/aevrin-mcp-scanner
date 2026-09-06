import type { Finding, Severity } from "./types";

/** How much one finding of this severity adds to the 0-100 risk score.
 *  Mirrors SEVERITY_WEIGHTS in the backend's `mcp/risk.py`; risk counts up,
 *  so these are additions, not the deductions the old score used. */
export function riskImpactForSeverity(severity: Severity) {
  if (severity === "critical") return "+25";
  if (severity === "high") return "+15";
  if (severity === "medium") return "+8";
  if (severity === "low") return "+2";
  return "No risk impact";
}

export function summarizeFindings(findings: Finding[]): Record<Severity, number> {
  const counts: Record<Severity, number> = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
  for (const finding of findings) counts[finding.severity] += 1;
  return counts;
}
