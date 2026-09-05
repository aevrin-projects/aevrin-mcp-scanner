/** What a scan can be pointed at. `local_path` only ever arrives from the
 *  CLI or the hook, so the dashboard's own picker excludes it. */
export type TargetType = "github_repo" | "live_mcp_server" | "config_paste" | "local_path";
export type DashboardTargetType = Exclude<TargetType, "local_path">;
export type ScanSource = "dashboard" | "cli" | "hook";
export type ScanStatus = "queued" | "running" | "completed" | "failed" | "incomplete";
export type StageStatus = "pending" | "running" | "done" | "failed" | "skipped";
export type StageName =
  | "cloning"
  | "discovery"
  | "mcp_rules"
  | "mcp_behavior"
  | "secrets"
  | "dependencies"
  | "aggregating";

/** A-F, or null when coverage was incomplete. Null is a state to render, not
 *  a missing value: a scan that could not read a server's tools has no
 *  evidence to make a claim from, and showing nothing there would read as a
 *  loading state rather than as "we could not tell". */
export type Grade = "A" | "B" | "C" | "D" | "F";

/** What the report answers, in the order a reader needs it. Computed by the
 *  backend's single grader so the dashboard, the CLI and the exported report
 *  never disagree about the same scan. */
export interface RiskSummary {
  headline: string;
  explanation: string;
  potential_impact: string;
  recommended_action: string;
  suggested_policy: string;
}

export interface Scan {
  id: string;
  target_type: TargetType;
  target: string;
  status: ScanStatus;
  source: ScanSource;
  /** 0-100, higher is worse. The inverse of the old `score`, which counted
   *  down from 100 - see the backend's mcp/risk.py. */
  risk_score: number | null;
  grade: Grade | null;
  error: string | null;
  mcp_detected: boolean | null;
  unreliable_stages: StageName[];
  /** Set when AI review covered only part of the findings (per-scan cap). */
  triage_note: string | null;
  /** Derived server-side from this scan's own findings. Present only on the
   *  single-scan response; a list response has no findings loaded to derive
   *  it from. */
  risk_summary: RiskSummary | null;
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

/** What changed between this scan and the previous scan of the same target.
 *  Matching is (title, file_path, tool), the same triple used to
 *  decide whether a patch cleared a finding, so the two always agree. */
export type ScanDiffEntry = { title: string; file_path: string | null; tool: string };

export type ScanDiff = {
  previous_scan_id: string | null;
  resolved: ScanDiffEntry[];
  introduced: ScanDiffEntry[];
  unchanged_count: number;
};
