export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type TriageStatus = "open" | "fixed" | "false_positive";

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
  additional_locations: {
    file_path: string | null;
    line_start: number | null;
    line_end: number | null;
    manifest_field: string | null;
  }[];
  llm_classification: string | null;
  llm_severity: Severity | null;
  llm_reasoning: string | null;
  llm_remediation: string | null;
  llm_triaged_at: string | null;
  autofix_status: "none" | "queued" | "in_progress" | "fixed" | "failed";
  /** Which step of an in-flight fix is running. Null once terminal. */
  autofix_stage: "analysing" | "generating" | "verifying" | "authorizing" | "opening_pr" | null;
  autofix_pr_url: string | null;
  autofix_failure_reason: string | null;
}

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
