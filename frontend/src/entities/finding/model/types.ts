export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type TriageStatus = "open" | "fixed" | "false_positive";

export interface Finding {
  id: string;
  scan_id: string;
  tool: string;
  /** The rule that produced this, e.g. "AS-006". The rule catalogue is the
   *  only place that says what an id means, so a finding carries the id and
   *  its evidence and the prose is looked up. Null for a finding whose
   *  producing tool has no rule identity of its own. */
  rule_id: string | null;
  /** "Why this matters", from the rule catalogue. Null for a finding whose
   *  rule id this build does not know - never generic filler. */
  impact: string | null;
  /** The specific facts that made the rule fire: matched text, a capability,
   *  an input property, a package version. A finding with no evidence is an
   *  assertion, and this product does not ship assertions. */
  evidence: string[];
  /** Every declared MCP tool this finding applies to. More than one once
   *  identical rule verdicts have been folded into a single card. */
  affected_tools: string[];
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

