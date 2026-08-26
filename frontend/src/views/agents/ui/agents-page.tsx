"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Bot, ChevronRight, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { ApiError } from "@/shared/api";
import { agentApi, AGENT_KIND_LABELS, PolicyBadge, RiskBadge, RISK_ORDER } from "@/entities/agent";
import type { AgentSummary } from "@/entities/agent";
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
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { formatDateTime } from "@/shared/lib/format";
import { CopyButton } from "@/shared/ui/copy-button";

const ENROL_COMMAND = "aevrin agent scan --upload";

export function AgentsPage() {
  const [agents, setAgents] = useState<AgentSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [forgetting, setForgetting] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    agentApi
      .listAgents()
      .then((result) => {
        if (cancelled) return;
        setAgents([...result].sort((a, b) => RISK_ORDER[a.risk] - RISK_ORDER[b.risk]));
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load your agents.");
        setAgents([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  async function forget(agent: AgentSummary) {
    const confirmed = window.confirm(
      `Forget ${agent.agent_name} on ${agent.hostname}?\n\n` +
        "This removes Aevrin's copy of what that machine reported. Nothing on the machine changes, " +
        "and the next `aevrin agent scan --upload` from it will report it again.",
    );
    if (!confirmed) return;
    setForgetting(agent.id);
    try {
      await agentApi.forgetAgent(agent.id);
      setAgents((current) => current?.filter((entry) => entry.id !== agent.id) ?? []);
      toast.success("Agent forgotten");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not forget this agent.");
    } finally {
      setForgetting(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        pretitle="AI security"
        title="Agents"
        description="The AI coding agents that have reported in, and what each has been allowed to do on the machine it runs on."
      />

      {/* Stated once, up front. A security product that leaves people guessing
          whether a page can act on their machine is a product they will not
          trust when it says something more serious. */}
      <Alert>
        <AlertTitle>Read-only</AlertTitle>
        <AlertDescription>
          Aevrin cannot reach your machine or change any agent configuration from here. Everything on
          this page is what a device reported the last time you ran{" "}
          <code className="font-mono text-[13px]">{ENROL_COMMAND}</code> on it.
        </AlertDescription>
      </Alert>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load agents</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {agents === null ? (
        <Panel>
          <PanelBody className="flex flex-col gap-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </PanelBody>
        </Panel>
      ) : agents.length === 0 && !error ? (
        <Panel>
          <EmptyState
            icon={<Bot />}
            title="No agent has reported yet"
            body={
              <>
                Run this on any machine where you use an AI coding agent. It reads configuration only:
                nothing is executed, and no credential value is ever sent.
              </>
            }
            action={
              <span className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-[13px]">
                {ENROL_COMMAND}
                <CopyButton value={ENROL_COMMAND} />
              </span>
            }
          />
        </Panel>
      ) : agents.length === 0 ? null : (
        <Panel>
          <PanelTableWrap>
            <Table>
              <THead>
                <TR>
                  <TH>Agent</TH>
                  <TH>Device</TH>
                  <TH>Posture</TH>
                  <TH className="text-right">MCP</TH>
                  <TH className="text-right">Skills</TH>
                  <TH className="text-right">Hooks</TH>
                  <TH>Last reported</TH>
                  <TH className="text-right">Actions</TH>
                </TR>
              </THead>
              <TBody>
                {agents.map((agent) => (
                  <TR key={agent.id}>
                    <TD>
                      <Link
                        href={`/agents/${agent.id}`}
                        className="flex items-center gap-1 font-medium hover:underline"
                      >
                        {AGENT_KIND_LABELS[agent.agent_type] ?? agent.agent_name}
                        <ChevronRight className="size-3.5 text-muted-foreground" aria-hidden="true" />
                      </Link>
                      <span className="text-xs text-muted-foreground">
                        {agent.agent_version ? `v${agent.agent_version}` : "version unknown"}
                      </span>
                    </TD>
                    <TD>
                      <span className="font-medium">{agent.hostname}</span>
                      <span className="block text-xs text-muted-foreground">
                        {agent.platform ?? "platform unknown"}
                      </span>
                    </TD>
                    <TD>
                      <span className="flex items-center gap-2">
                        <span className="font-medium tabular-nums">{agent.posture_score}/100</span>
                        <RiskBadge risk={agent.risk} />
                        <PolicyBadge policy={agent.policy} />
                      </span>
                      {/* Confidence sits beside the number rather than
                          inside it: a 90 from complete evidence and a 90 with
                          half the config unreadable are not the same claim. */}
                      <span className="block text-xs text-muted-foreground">
                        {agent.coverage_complete ? "Complete coverage" : "Incomplete coverage"} ·{" "}
                        {agent.confidence} confidence
                      </span>
                    </TD>
                    <TD className="text-right tabular-nums">{agent.mcp_server_count}</TD>
                    <TD className="text-right tabular-nums">{agent.skill_count}</TD>
                    <TD className="text-right tabular-nums">{agent.hook_count}</TD>
                    <TD className="text-muted-foreground">{formatDateTime(agent.reported_at)}</TD>
                    <TD className="text-right">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Forget ${agent.agent_name} on ${agent.hostname}`}
                        disabled={forgetting === agent.id}
                        onClick={() => void forget(agent)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </TD>
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
