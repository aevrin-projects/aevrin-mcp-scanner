import type { ScanStatus, StageName, TargetType } from "./types";

export const STAGE_ORDER: StageName[] = [
  "cloning",
  "static_analysis",
  "secrets",
  "dependencies",
  "mcp_analysis",
  "tool_description_check",
  "aggregating",
];

export const STAGE_LABELS: Record<StageName, string> = {
  cloning: "Cloning",
  static_analysis: "Static analysis",
  secrets: "Secrets",
  dependencies: "Dependencies",
  mcp_analysis: "MCP behavior analysis",
  tool_description_check: "Tool description check",
  aggregating: "Aggregating",
};

export const TARGET_TYPE_LABELS: Record<TargetType, string> = {
  github_repo: "GitHub repository",
  live_mcp_server: "Live MCP server",
  config_paste: "Pasted configuration",
  local_path: "Local path",
};

/** Shorter forms for the target picker, where the surrounding UI already
 *  makes it clear these are scan targets. */
export const TARGET_MODE_LABELS: Record<Exclude<TargetType, "local_path">, string> = {
  github_repo: "GitHub repo",
  live_mcp_server: "Live server",
  config_paste: "Paste config",
};

export const SCAN_SOURCE_LABELS = {
  dashboard: "Dashboard scan",
  cli: "CLI scan",
  hook: "Hook scan",
} as const;

export const SCAN_STATUS_LABELS: Record<ScanStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Complete",
  failed: "Failed",
  incomplete: "Partial",
};
