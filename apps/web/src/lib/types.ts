export type TargetType = "github_repo" | "live_mcp_server" | "config_paste" | "local_path";
export type DashboardTargetType = Exclude<TargetType, "local_path">;
export type ScanSource = "dashboard" | "cli" | "hook";
export type ScanStatus = "queued" | "running" | "completed" | "failed" | "incomplete";
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
  source: ScanSource;
  score: number | null;
  error: string | null;
  mcp_detected: boolean | null;
  unreliable_stages: StageName[];
  /** Set when AI review covered only part of the findings (per-scan cap). */
  triage_note: string | null;
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
  triage_reason: string | null;
  triaged_at: string | null;
  created_at: string;
  excluded_path: boolean;
  confidence: string | null;
  original_severity: Severity | null;
  epss_score: number | null;
  in_kev: boolean;
  dependency_scope: string | null;
  corroborated_by: string[];
  occurrence_count: number;
  additional_locations: { file_path: string | null; line_start: number | null; line_end: number | null; manifest_field: string | null }[];
  llm_classification: string | null;
  llm_severity: Severity | null;
  llm_reasoning: string | null;
  llm_remediation: string | null;
  llm_model: string | null;
  llm_triaged_at: string | null;
  autofix_status: "none" | "queued" | "in_progress" | "fixed" | "failed";
  autofix_pr_url: string | null;
  autofix_failure_reason: string | null;
}

export interface ApiKey {
  id: number;
  name: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export type UsageBucket = "cli" | "hook" | "dashboard" | "auto_fix";

export interface BucketUsage {
  bucket: UsageBucket;
  used: number;
  limit: number | null; // null = unlimited (Team)
  resets_at: string;
}

export interface AccountUsage {
  tier: "free" | "hobby" | "team";
  paid_until: string | null;
  buckets: BucketUsage[];
  activity: UsageActivity[];
}

export interface UsageActivity {
  id: string;
  source: ScanSource;
  target_type: TargetType;
  target: string;
  status: ScanStatus;
  score: number | null;
  created_at: string;
  completed_at: string | null;
}

export interface Subscription {
  tier: "free" | "hobby" | "pro" | "team";
  effective_tier: "free" | "hobby" | "pro" | "team";
  paid_until: string | null;
}

export interface Payment {
  id: string;
  tier: "hobby" | "pro" | "team" | "autofix_addon";
  cycle: "monthly" | "annual";
  seats: number;
  byok: boolean;
  amount_paise: number;
  currency: string;
  status: "created" | "paid" | "failed";
  created_at: string;
  verified_at: string | null;
}

/** One repository the connected GitHub App installation can reach.
 *  `looks_like_mcp` is a label, never a gate: `null` means the check could
 *  not run, and `false` only means the heuristic didn't recognise it — the
 *  repo is still scannable. */
export type GithubRepo = {
  full_name: string;
  html_url: string;
  private: boolean;
  default_branch: string;
  pushed_at: string | null;
  looks_like_mcp: boolean | null;
};

export type GithubReposResponse = {
  connected: boolean;
  account_login: string | null;
  repos: GithubRepo[];
};

/** Result of fixing every eligible finding in one scan. Counts are per
 *  finding, and `pr_urls` holds one entry per PR actually opened. */
export type BulkFixResponse = {
  attempted: number;
  fixed: number;
  failed: number;
  skipped: number;
  pr_urls: string[];
  message: string;
};

/* --- admin panel ---------------------------------------------------------
 * Mirrors the response models in apps/api/src/aevrin_api/routers/admin.py.
 * Nothing here ever carries a credential: the API returns masked or derived
 * values only. */

export type AdminUserRow = {
  user_id: string;
  email: string | null;
  tier: string;
  effective_tier: string;
  status: "active" | "disabled" | "blocked";
  flagged: boolean;
  paid_until: string | null;
  created_at: string | null;
  last_scan_at: string | null;
  scans_this_period: number;
};

export type AdminUserPage = {
  rows: AdminUserRow[];
  total: number;
  page: number;
  page_size: number;
};

export type AdminUsageBucket = {
  bucket: string;
  used: number;
  limit: number | null;
  resets_at: string;
};

export type AdminQuotaOverride = {
  bucket: string;
  limit_value: number | null;
  expires_at: string | null;
  reason: string | null;
  created_at: string;
};

export type AdminUserDetail = {
  user_id: string;
  email: string | null;
  tier: string;
  effective_tier: string;
  status: "active" | "disabled" | "blocked";
  status_reason: string | null;
  flagged: boolean;
  paid_until: string | null;
  created_at: string | null;
  /** False for OAuth-only accounts, which have no password to reset. */
  has_password: boolean;
  auth_providers: string[];
  usage: AdminUsageBucket[];
  overrides: AdminQuotaOverride[];
  recent_scans: Array<Record<string, unknown>>;
  api_key_count: number;
  github_connected: boolean;
};

export type AdminAuditEntry = {
  id: number;
  actor_user_id: string;
  actor_email: string | null;
  action: string;
  target_user_id: string | null;
  target_email: string | null;
  target_resource: string | null;
  reason: string | null;
  metadata: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
};

export type AdminLoginAttempt = {
  id: number;
  email: string | null;
  succeeded: boolean;
  failure_reason: string | null;
  ip_address: string | null;
  created_at: string;
};

/** What changed between this scan and the previous scan of the same target.
 *  Matching is (title, file_path, tool), the same triple Fix It uses to
 *  decide whether a patch cleared a finding, so the two always agree. */
export type ScanDiffEntry = { title: string; file_path: string | null; tool: string };
export type ScanDiff = {
  previous_scan_id: string | null;
  resolved: ScanDiffEntry[];
  introduced: ScanDiffEntry[];
  unchanged_count: number;
};
