import { request } from "@/shared/api";
import type {
  AgentDetail,
  AgentSummary,
  AttackPath,
  McpAsset,
  Permission,
  PolicyAuditEntry,
  Policies,
  Skill,
} from "../model/types";

export const agentApi = {
  listAgents: () => request<AgentSummary[]>("/agents"),
  getAgent: (id: string) => request<AgentDetail>(`/agents/${id}`),
  listMcpServers: () => request<McpAsset[]>("/agents/mcp-servers"),
  listSkills: () => request<Skill[]>("/agents/skills"),
  listPermissions: () => request<Permission[]>("/agents/permissions"),
  listAttackPaths: () => request<AttackPath[]>("/agents/attack-paths"),
  getPolicies: () => request<Policies>("/agents/policies"),
  updatePolicies: (policies: Policies) =>
    request<Policies>("/agents/policies", { method: "PUT", body: JSON.stringify(policies) }),
  listPolicyAudit: () => request<PolicyAuditEntry[]>("/agents/policy-audit"),
  /** Forgets Aevrin's copy of what a device reported. The machine keeps its
   *  own configuration; nothing is changed there. */
  forgetAgent: (id: string) => request<void>(`/agents/${id}`, { method: "DELETE" }),
};
