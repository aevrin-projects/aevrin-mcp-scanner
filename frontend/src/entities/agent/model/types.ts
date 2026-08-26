/** Mirrors the API's agent posture models, which in turn mirror the
 *  scanner-core snapshot the CLI produces. One shape from device to page. */

export type AgentKind = "claude_code" | "codex" | "cursor" | "gemini_cli";
export type ConfigScope = "managed" | "user" | "project" | "local";
export type CapabilityName =
  | "filesystem_read"
  | "filesystem_write"
  | "shell"
  | "network"
  | "mcp_tool";
/** `unknown` is not `none`. Configuration that could not be read grants an
 *  unknown amount, and collapsing the two understates risk. */
export type CapabilityLevel = "none" | "ask" | "limited" | "full" | "unknown";
export type PostureRisk = "low" | "medium" | "high" | "critical";

export interface Evidence {
  detail: string;
  source_path: string;
  scope: ConfigScope | null;
}

export interface EffectiveCapability {
  capability: CapabilityName;
  level: CapabilityLevel;
  evidence: Evidence[];
  subject: string | null;
}

export interface McpServerRef {
  name: string;
  scope: ConfigScope;
  source_path: string;
  transport: string;
  command: string | null;
  args: string[];
  url: string | null;
  auto_approved: boolean;
}

export interface HookRef {
  event: string;
  matcher: string | null;
  command: string;
  source_path: string;
  scope: ConfigScope;
}

export interface RawPermission {
  rule: string;
  effect: "allow" | "ask" | "deny";
  scope: ConfigScope;
  source_path: string;
}

export interface SkillRef {
  name: string;
  scope: ConfigScope;
  source_path: string;
  description: string | null;
}

export interface PluginRef {
  name: string;
  source: string;
  install_location: string | null;
}

/** Presence and location only. There is no field for a value, by design. */
export interface CredentialRef {
  kind: string;
  present: boolean;
  source: string;
  location: string;
}

export interface Coverage {
  checked: string[];
  not_checked: string[];
  complete: boolean;
}

export interface AgentSnapshot {
  schema_version: string;
  agent: { type: AgentKind; name: string; version: string | null; install_path: string | null } | null;
  device: { hostname: string; platform: string; platform_version: string | null } | null;
  kind: AgentKind;
  config_paths: string[];
  project_root: string | null;
  default_permission_mode: string | null;
  capabilities: EffectiveCapability[];
  mcp_servers: McpServerRef[];
  hooks: HookRef[];
  permissions: RawPermission[];
  skills: SkillRef[];
  plugins: PluginRef[];
  credentials: CredentialRef[];
  coverage: Coverage;
  unreadable_paths: string[];
}

export interface AgentSummary {
  id: string;
  agent_type: AgentKind;
  agent_name: string;
  agent_version: string | null;
  device_id: string;
  hostname: string;
  platform: string | null;
  reported_at: string;
  risk: PostureRisk;
  risk_reasons: string[];
  mcp_server_count: number;
  skill_count: number;
  plugin_count: number;
  hook_count: number;
  coverage_complete: boolean;
}

export interface AgentDetail extends AgentSummary {
  snapshot: AgentSnapshot;
}

export type TrustGrade = "A" | "B" | "C" | "D";

export interface GradeFactor {
  points: number;
  reason: string;
}

/** Present only when a scan of this exact target actually ran. A grade is a
 *  claim about evidence, so there is no value here meaning "probably fine". */
export interface McpTrust {
  scan_id: string;
  scanned_at: string;
  scan_score: number | null;
  grade: TrustGrade;
  label: string;
  recommended_action: string;
  factors: GradeFactor[];
}

export interface McpServerInventoryItem {
  name: string;
  scope: ConfigScope;
  transport: string;
  command: string | null;
  url: string | null;
  auto_approved: boolean;
  source_path: string;
  project_root: string | null;
  agent_id: string;
  agent_type: AgentKind;
  agent_name: string;
  hostname: string;
  reported_at: string;
  trust: McpTrust | null;
}
