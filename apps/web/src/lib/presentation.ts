import type { Finding, Scan, ScanStage, ScanStatus, Severity, TargetType } from "@/lib/types";

export const TARGET_TYPE_LABELS: Record<TargetType, string> = {
  github_repo: "GitHub repository",
  live_mcp_server: "Live MCP server",
  config_paste: "Pasted configuration",
};

export const TARGET_MODE_LABELS: Record<TargetType, string> = {
  github_repo: "GitHub repo",
  live_mcp_server: "Live server",
  config_paste: "Paste config",
};

export const SCAN_STATUS_LABELS: Record<ScanStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Complete",
  failed: "Failed",
  incomplete: "Partial",
};

export const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

export function formatDateTime(value: string | null) {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDate(value: string | null) {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

export function formatDuration(start: string, end: string | null) {
  const startMs = new Date(start).getTime();
  const endMs = new Date(end ?? Date.now()).getTime();
  const totalSeconds = Math.max(0, Math.round((endMs - startMs) / 1000));

  if (totalSeconds < 60) return `${totalSeconds}s`;

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes < 60) {
    return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

export function severityLabel(value: Severity) {
  return value === "info" ? "Info" : value[0].toUpperCase() + value.slice(1);
}

export function scoreImpactForSeverity(severity: Severity) {
  if (severity === "critical") return "-40";
  if (severity === "high") return "-20";
  if (severity === "medium") return "-8";
  if (severity === "low") return "-3";
  return "No score impact";
}

export function summarizeFindings(findings: Finding[]) {
  const counts = {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    info: 0,
  } satisfies Record<Severity, number>;

  for (const finding of findings) {
    counts[finding.severity] += 1;
  }

  return counts;
}

export function summarizeCoverage(stages: ScanStage[]) {
  return {
    completed: stages.filter((stage) => stage.status === "done").length,
    failed: stages.filter((stage) => stage.status === "failed").length,
    skipped: stages.filter((stage) => stage.status === "skipped").length,
    running: stages.filter((stage) => stage.status === "running").length,
    queued: stages.filter((stage) => stage.status === "pending").length,
  };
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

export function uniqueTargets(scans: Scan[]) {
  return new Set(scans.map((scan) => scan.target)).size;
}
