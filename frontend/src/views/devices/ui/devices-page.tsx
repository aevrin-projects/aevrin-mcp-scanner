"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Laptop } from "lucide-react";
import { ApiError } from "@/shared/api";
import { agentApi, AGENT_KIND_LABELS, groupByDevice, RiskBadge } from "@/entities/agent";
import type { Device } from "@/entities/agent";
import {
  EmptyState,
  PageHeader,
  Panel,
  PanelBody,
  PanelTableWrap,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
} from "@/shared/ui";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Skeleton } from "@/shared/ui/skeleton";
import { formatDateTime } from "@/shared/lib/format";

export function DevicesPage() {
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    agentApi
      .listAgents()
      .then((agents) => {
        if (!cancelled) setDevices(groupByDevice(agents));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load your devices.");
        setDevices([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        pretitle="AI security"
        title="Devices"
        description="Every machine that has reported an agent, rated by the least restricted agent on it."
      />

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load devices</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {devices === null ? (
        <Panel>
          <PanelBody className="flex flex-col gap-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </PanelBody>
        </Panel>
      ) : devices.length === 0 && !error ? (
        <Panel>
          <EmptyState
            icon={<Laptop />}
            title="No devices reported"
            body="A device appears here after you run `aevrin agent scan --upload` on it."
          />
        </Panel>
      ) : devices.length === 0 ? null : (
        <Panel>
          <PanelTableWrap>
            <Table>
              <THead>
                <TR>
                  <TH>Device</TH>
                  <TH>Agents</TH>
                  <TH>Posture</TH>
                  <TH>Last reported</TH>
                </TR>
              </THead>
              <TBody>
                {devices.map((device) => (
                  <TR key={device.device_id}>
                    <TD>
                      <span className="font-medium">{device.hostname}</span>
                      <span className="block text-xs text-muted-foreground">
                        {device.platform ?? "platform unknown"}
                      </span>
                    </TD>
                    <TD>
                      <span className="flex flex-wrap gap-x-2 gap-y-1 text-sm">
                        {device.agents.map((agent) => (
                          <Link
                            key={agent.id}
                            href={`/agents/${agent.id}`}
                            className="hover:underline"
                          >
                            {AGENT_KIND_LABELS[agent.agent_type] ?? agent.agent_name}
                          </Link>
                        ))}
                      </span>
                    </TD>
                    <TD>
                      {/* The worst agent on a machine is the machine's risk.
                          Averaging would let one tidy agent hide the one that
                          can reach everything. */}
                      <span className="flex items-center gap-2">
                        <span className="font-medium tabular-nums">{device.lowest_score}/100</span>
                        <RiskBadge risk={device.worst_risk} />
                      </span>
                    </TD>
                    <TD className="text-muted-foreground">{formatDateTime(device.last_reported)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </PanelTableWrap>
        </Panel>
      )}
    </div>
  );
}
