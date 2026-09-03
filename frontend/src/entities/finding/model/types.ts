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
  /** Which declared MCP tool this finding's sink was found inside
   * (analysis.capability_map). Null when not applicable or not
   * established - never a guess at the nearest tool. */
  mcp_tool: string | null;
  /** The normalized capability vocabulary term this finding is about
   * (adapters/mcp_behavior.py). Null for every tool except the MCP
   * behavior pack. */
  capability: string | null;
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
}

