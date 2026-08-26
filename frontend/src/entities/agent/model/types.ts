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
  /** Vendor wording: "bypassPermissions" for Claude Code,
   *  "workspace-write/never" for Codex. */
  default_permission_mode: string | null;
  /** True when nothing this agent does is put to a human first. Normalised by
   *  the adapter, so nothing above it has to know each vendor's spelling. */
  unattended: boolean;
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

export interface PostureFactor {
  points: number;
  reason: string;
}

/** How much the posture score itself can be relied on. Separate from the
 *  score: a 90 from complete evidence and a 90 with half the config
 *  unreadable are not the same claim. */
export type Confidence = "high" | "medium" | "low";

export interface AgentSummary {
  id: string;
  agent_type: AgentKind;
  agent_name: string;
  agent_version: string | null;
  device_id: string;
  hostname: string;
  platform: string | null;
  reported_at: string;
  /** Distinct from the MCP scan score and the MCP trust grade. */
  posture_score: number;
  risk: PostureRisk;
  confidence: Confidence;
  risk_factors: PostureFactor[];
  mcp_server_count: number;
  skill_count: number;
  plugin_count: number;
  hook_count: number;
  coverage_complete: boolean;
  /** Absent when no policy is switched on. */
  policy: PolicyOutcome | null;
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

/** One place a server is configured: one agent, on one device, at one scope. */
export interface McpInstallation {
  agent_id: string;
  agent_type: AgentKind;
  agent_name: string;
  device_id: string;
  hostname: string;
  name: string;
  scope: ConfigScope;
  project_root: string | null;
  source_path: string;
  transport: string;
  command: string | null;
  url: string | null;
  enabled: boolean;
  auto_approved: boolean;
  reported_at: string;
}

/** How far the correlation can be trusted. `low` means "we could not tell
 *  these apart from a name", and such servers are deliberately never merged. */
export type IdentityConfidence = "high" | "medium" | "low";

/** One MCP server, however many places it is configured. */
export interface McpAsset {
  identity_key: string;
  identity_kind: string;
  identity_label: string;
  identity_confidence: IdentityConfidence;
  name: string;
  transport: string;
  url: string | null;
  command: string | null;
  installation_count: number;
  device_count: number;
  agent_count: number;
  project_count: number;
  scopes: ConfigScope[];
  enabled_everywhere: boolean;
  installations: McpInstallation[];
  trust: McpTrust | null;
  policy: PolicyOutcome | null;
}

export interface Skill {
  name: string;
  description: string | null;
  scope: ConfigScope;
  source_path: string;
  agent_id: string;
  agent_type: AgentKind;
  hostname: string;
}

export interface Permission {
  rule: string;
  effect: "allow" | "ask" | "deny";
  scope: ConfigScope;
  source_path: string;
  agent_id: string;
  agent_type: AgentKind;
  hostname: string;
}

/** Derived from the agent list rather than fetched: a device is the machine
 *  its agents were reported from, and a separate endpoint would be the same
 *  rows grouped differently. */
export interface Device {
  device_id: string;
  hostname: string;
  platform: string | null;
  agents: AgentSummary[];
  worst_risk: PostureRisk;
  lowest_score: number;
  last_reported: string;
}

export interface AttackStep {
  label: string;
  detail: string;
  evidence: string[];
}

/** Present only when every step was read out of a configuration. A chain of
 *  maybes looks like a finding and is not one. */
export interface AttackPath {
  key: string;
  title: string;
  source: string;
  target: string;
  severity: "critical" | "high" | "medium";
  confidence: "high" | "medium";
  steps: AttackStep[];
  remediation: string;
  agent_id: string;
  agent_type: AgentKind;
  hostname: string;
}

/** All off until someone turns them on. A grade is a recommendation; this is
 *  where a person decides it should be enforcement. */
export interface Policies {
  block_grade_d: boolean;
  require_approval_grade_c: boolean;
  block_unattended_shell: boolean;
  block_unrestricted_network: boolean;
}

export type PolicyDecision = "allowed" | "approval_required" | "blocked";

/** Absent when no policy is switched on: rendering "allowed" for an account
 *  with no policies would imply a review that never happened. */
export interface PolicyOutcome {
  decision: PolicyDecision;
  reasons: string[];
}

export interface PolicyAuditEntry {
  id: number;
  actor: string;
  action: string;
  before: Policies | null;
  after: Policies | null;
  created_at: string;
}
