export type TargetType = "github_repo" | "live_mcp_server" | "config_paste";
export type ScanStatus = "queued" | "running" | "completed" | "failed";
export type StageStatus = "pending" | "running" | "done" | "failed" | "skipped";
export type StageName =
  | "cloning"
  | "static_analysis"
  | "secrets"
  | "dependencies"
  | "tool_description_check"
  | "aggregating";
export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type TriageStatus = "open" | "fixed" | "false_positive";

export const STAGE_ORDER: StageName[] = [
  "cloning",
  "static_analysis",
  "secrets",
  "dependencies",
  "tool_description_check",
  "aggregating",
];

export const STAGE_LABELS: Record<StageName, string> = {
  cloning: "Cloning",
  static_analysis: "Static analysis",
  secrets: "Secrets",
  dependencies: "Dependencies",
  tool_description_check: "Tool description check",
  aggregating: "Aggregating",
};

export const OWASP_CATEGORY_LABELS: Record<string, string> = {
  MCP01: "Token Mismanagement & Secret Exposure",
  MCP02: "Tool Poisoning (Hidden Instructions)",
  MCP03: "Cross-Origin Escalation / Tool Shadowing",
  MCP04: "Rug Pull (Tool Drift After Install)",
  MCP05: "Command Injection, Path Traversal, SSRF, File Access",
  MCP06: "Missing/Weak Authentication",
  MCP07: "Supply Chain / Malicious or Typosquatted Dependencies",
  MCP08: "Prompt Injection via Live Tool Responses",
  MCP09: "Excessive Agency / Overprivileged Scope",
  MCP10: "Weak/Missing Audit Logging",
};

export interface Scan {
  id: string;
  target_type: TargetType;
  target: string;
  status: ScanStatus;
  score: number | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface ScanStage {
  name: StageName;
  status: StageStatus;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface Finding {
  id: string;
  scan_id: string;
  tool: string;
  owasp_category: string;
  severity: Severity;
  title: string;
  description: string;
  file_path: string | null;
  line_start: number | null;
  line_end: number | null;
  manifest_field: string | null;
  tool_name_in_manifest: string | null;
  remediation: string;
  verified: boolean | null;
  not_tested: boolean;
  triage_status: TriageStatus;
  created_at: string;
}

export interface ApiKey {
  id: number;
  name: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}
