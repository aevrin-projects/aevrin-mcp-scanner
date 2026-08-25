/** What a scan can be pointed at. `local_path` only ever arrives from the
 *  CLI or the hook, so the dashboard's own picker excludes it. */
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
