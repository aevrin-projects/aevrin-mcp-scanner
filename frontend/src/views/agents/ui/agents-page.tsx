"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Bot, ChevronRight, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { ApiError } from "@/shared/api";
import { agentApi, AGENT_KIND_LABELS, RiskBadge, RISK_ORDER } from "@/entities/agent";
import type { AgentSummary } from "@/entities/agent";
import { WORKSPACE_PERMISSIONS, useWorkspacePermission, workspaceAuthor } from "@/entities/organization";
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
  const removeAgents = useWorkspacePermission(WORKSPACE_PERMISSIONS.agentsDelete);

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
        setError(err instanceof ApiError ? err.message : "We could not load your agents.");
        setAgents([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  async function forget(agent: AgentSummary) {
    const confirmed = window.confirm(
      `Remove ${agent.agent_name} on ${agent.hostname} from Aevrin?\n\n` +
        "This only deletes what that computer reported to Aevrin. Nothing on the computer changes, " +
        "and running `aevrin agent scan --upload` there again will add it back.",
    );
    if (!confirmed) return;
    setForgetting(agent.id);
    try {
      await agentApi.forgetAgent(agent.id);
      setAgents((current) => current?.filter((entry) => entry.id !== agent.id) ?? []);
      toast.success("Agent removed from Aevrin");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "We could not remove this agent.");
    } finally {
      setForgetting(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        pretitle="AI security"
        title="Agents"
        description="The AI coding agents Aevrin has checked, and what each one is allowed to do on its computer. The safety score goes from 0 to 100, and higher is safer."
      />

      {/* Stated once, up front. A security product that leaves people guessing
          whether a page can act on their machine is a product they will not
          trust when it says something more serious. */}
      <Alert>
        <AlertTitle>Aevrin can only look, not change</AlertTitle>
        <AlertDescription>
          Aevrin cannot reach your computer or change an agent&apos;s settings from here. This page shows
          what each computer reported the last time you ran{" "}
          <code className="font-mono text-[13px]">{ENROL_COMMAND}</code> on it.
        </AlertDescription>
      </Alert>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>We could not load your agents</AlertTitle>
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
            title="No agent has been checked yet"
            body={
              <>
                Run this on any computer where you use an AI coding agent. It only reads settings: it
                runs nothing, and it never sends a password or key.
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
                  <TH>Computer</TH>
                  <TH>How safe</TH>
                  <TH className="text-right">MCP servers</TH>
                  <TH className="text-right">Skills</TH>
                  <TH className="text-right">Hooks</TH>
                  <TH>Last checked</TH>
                  {removeAgents.allowed ? <TH className="text-right">Actions</TH> : null}
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
                        {agent.agent_version ? `v${agent.agent_version}` : "Version not known"}
                      </span>
                    </TD>
                    <TD>
                      <span className="font-medium">{agent.hostname}</span>
                      <span className="block text-xs text-muted-foreground">
                        {agent.platform ?? "System not known"}
                        {workspaceAuthor(agent) ? ` · reported by ${workspaceAuthor(agent)}` : ""}
                      </span>
                    </TD>
                    <TD>
                      <span className="flex items-center gap-2">
                        <span className="font-medium tabular-nums">{agent.posture_score}/100</span>
                        <RiskBadge risk={agent.risk} />
                      </span>
                      {/* Confidence sits beside the number rather than
                          inside it: a 90 from complete evidence and a 90 with
                          half the config unreadable are not the same claim. */}
                      <span className="block text-xs text-muted-foreground">
                        {agent.coverage_complete ? "All settings read" : "Some settings could not be read"}
                      </span>
                    </TD>
                    <TD className="text-right tabular-nums">{agent.mcp_server_count}</TD>
                    <TD className="text-right tabular-nums">{agent.skill_count}</TD>
                    <TD className="text-right tabular-nums">{agent.hook_count}</TD>
                    <TD className="text-muted-foreground">{formatDateTime(agent.reported_at)}</TD>
                    {removeAgents.allowed ? (
                      <TD className="text-right">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Remove ${agent.agent_name} on ${agent.hostname} from Aevrin`}
                          disabled={forgetting === agent.id}
                          onClick={() => void forget(agent)}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </TD>
                    ) : null}
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
