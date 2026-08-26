import { request } from "@/shared/api";
import type { AgentDetail, AgentSummary, McpAsset } from "../model/types";

export const agentApi = {
  listAgents: () => request<AgentSummary[]>("/agents"),
  getAgent: (id: string) => request<AgentDetail>(`/agents/${id}`),
  listMcpServers: () => request<McpAsset[]>("/agents/mcp-servers"),
  /** Forgets Aevrin's copy of what a device reported. The machine keeps its
   *  own configuration; nothing is changed there. */
  forgetAgent: (id: string) => request<void>(`/agents/${id}`, { method: "DELETE" }),
};
