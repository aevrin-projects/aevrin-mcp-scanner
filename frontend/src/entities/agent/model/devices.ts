import { RISK_ORDER } from "./labels";
import type { AgentSummary, Device } from "./types";

/**
 * A device is the machine its agents were reported from. Derived here rather
 * than fetched, because a devices endpoint would return the same rows grouped
 * differently, and two sources for one fact is how two pages start disagreeing.
 */
export function groupByDevice(agents: AgentSummary[]): Device[] {
  const byDevice = new Map<string, AgentSummary[]>();
  for (const agent of agents) {
    byDevice.set(agent.device_id, [...(byDevice.get(agent.device_id) ?? []), agent]);
  }

  return [...byDevice.values()]
    .map((group) => {
      // The worst agent on a machine is the machine's risk. Averaging would
      // let one tidy agent hide the one that can reach everything.
      const worst = [...group].sort((a, b) => RISK_ORDER[a.risk] - RISK_ORDER[b.risk])[0];
      return {
        device_id: worst.device_id,
        hostname: worst.hostname,
        platform: group.find((a) => a.platform)?.platform ?? null,
        agents: group,
        worst_risk: worst.risk,
        lowest_score: Math.min(...group.map((a) => a.posture_score)),
        last_reported: group.map((a) => a.reported_at).sort().at(-1)!,
      };
    })
    .sort((a, b) => RISK_ORDER[a.worst_risk] - RISK_ORDER[b.worst_risk]);
}
