"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft } from "lucide-react";
import { ApiError } from "@/shared/api";
import {
  agentApi,
  AGENT_KIND_LABELS,
  CAPABILITY_LABELS,
  CAPABILITY_LEVEL_LABELS,
  RiskBadge,
  ScopeBadge,
} from "@/entities/agent";
import type { AgentDetail, CapabilityLevel } from "@/entities/agent";
import {
  EmptyState,
  PageHeader,
  Panel,
  PanelBody,
  PanelHeader,
  PanelSubtitle,
  PanelTableWrap,
  PanelTitle,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
} from "@/shared/ui";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import { formatDateTime } from "@/shared/lib/format";
import { cn } from "@/shared/lib/utils";

/** Unknown is not none. Configuration that could not be read grants an
 *  unknown amount, and showing it as "None" is how a posture report ends up
 *  quieter than the machine it describes. */
const LEVEL_CLASSES: Record<CapabilityLevel, string> = {
  none: "text-muted-foreground",
  ask: "text-foreground",
  limited: "text-severity-medium",
  full: "text-severity-critical",
  unknown: "text-severity-high",
};

function Empty({ what }: { what: string }) {
  return <EmptyState title={`No ${what} found`} body={`This agent reported no ${what}.`} />;
}

export function AgentDetailPage({ agentId }: { agentId: string }) {
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    agentApi
      .getAgent(agentId)
      .then((result) => {
        if (!cancelled) setAgent(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load this agent.");
      });
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  if (error) {
    return (
      <div className="flex flex-col gap-6">
        <Button nativeButton={false} render={<Link href="/agents" />} variant="ghost" size="sm" className="w-fit">
          <ArrowLeft className="size-4" />
          All agents
        </Button>
        <Alert variant="destructive">
          <AlertTitle>Could not load this agent</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const snapshot = agent.snapshot;

  return (
    <div className="flex flex-col gap-6">
      <Button nativeButton={false} render={<Link href="/agents" />} variant="ghost" size="sm" className="w-fit">
        <ArrowLeft className="size-4" />
        All agents
      </Button>

      <PageHeader
        pretitle={`${agent.hostname}${agent.platform ? ` · ${agent.platform}` : ""}`}
        title={AGENT_KIND_LABELS[agent.agent_type] ?? agent.agent_name}
        description={
          <>
            {agent.agent_version ? `Version ${agent.agent_version}. ` : null}
            Last reported {formatDateTime(agent.reported_at)}.
          </>
        }
        actions={<RiskBadge risk={agent.risk} />}
      />

      {/* Why the risk is what it is, in the same words the CLI uses. A rating
          nobody can interrogate is an opinion with better typography. */}
      <Panel>
        <PanelHeader>
          <PanelTitle>Why this rating</PanelTitle>
          <PanelSubtitle>Derived from configuration alone. No scanner has to have run.</PanelSubtitle>
        </PanelHeader>
        <PanelBody>
          <ul className="flex flex-col gap-2">
            {agent.risk_reasons.map((reason) => (
              <li key={reason} className="flex gap-2 text-sm">
                <span aria-hidden="true" className="text-muted-foreground">
                  •
                </span>
                {reason}
              </li>
            ))}
          </ul>
        </PanelBody>
      </Panel>

      {snapshot.default_permission_mode === "bypassPermissions" ? (
        <Alert variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>Permission checks are switched off</AlertTitle>
          <AlertDescription>
            This agent runs with <code className="font-mono">bypassPermissions</code>, so nothing in its
            permission rules is enforced. Every capability below is unrestricted regardless of what the
            rules say.
          </AlertDescription>
        </Alert>
      ) : null}

      {!agent.coverage_complete ? (
        <Alert>
          <AlertTitle>Incomplete coverage</AlertTitle>
          <AlertDescription>
            Some configuration could not be read, so this is incomplete rather than clean.
            {snapshot.unreadable_paths.length > 0 ? (
              <span className="mt-2 block font-mono text-xs">{snapshot.unreadable_paths.join(", ")}</span>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : null}

      <Tabs defaultValue="capabilities">
        <TabsList>
          <TabsTrigger value="capabilities">Capabilities</TabsTrigger>
          <TabsTrigger value="mcp">MCP ({snapshot.mcp_servers.length})</TabsTrigger>
          <TabsTrigger value="skills">Skills ({snapshot.skills.length})</TabsTrigger>
          <TabsTrigger value="plugins">Plugins ({snapshot.plugins.length})</TabsTrigger>
          <TabsTrigger value="hooks">Hooks ({snapshot.hooks.length})</TabsTrigger>
          <TabsTrigger value="permissions">Rules ({snapshot.permissions.length})</TabsTrigger>
          <TabsTrigger value="credentials">Credentials ({snapshot.credentials.length})</TabsTrigger>
          <TabsTrigger value="sources">Sources</TabsTrigger>
        </TabsList>

        <TabsContent value="capabilities">
          <Panel>
            <PanelHeader>
              <PanelTitle>Effective capabilities</PanelTitle>
              <PanelSubtitle>
                The widest grant across every configuration file, not the winner of precedence:
                precedence decides which setting applies, it does not narrow what the agent can reach.
              </PanelSubtitle>
            </PanelHeader>
            <PanelTableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>Capability</TH>
                    <TH>Level</TH>
                    <TH>Evidence</TH>
                  </TR>
                </THead>
                <TBody>
                  {snapshot.capabilities.map((capability) => (
                    <TR key={`${capability.capability}:${capability.subject ?? ""}`}>
                      <TD className="font-medium">
                        {CAPABILITY_LABELS[capability.capability]}
                        {capability.subject ? (
                          <span className="block text-xs text-muted-foreground">{capability.subject}</span>
                        ) : null}
                      </TD>
                      <TD className={cn("font-medium", LEVEL_CLASSES[capability.level])}>
                        {CAPABILITY_LEVEL_LABELS[capability.level]}
                      </TD>
                      <TD>
                        {capability.evidence.length === 0 ? (
                          <span className="text-xs text-muted-foreground">No rule granted this.</span>
                        ) : (
                          <ul className="flex flex-col gap-1">
                            {capability.evidence.map((item) => (
                              <li key={`${item.source_path}:${item.detail}`} className="text-xs">
                                <span className="font-mono">{item.detail}</span>
                                <span className="block text-muted-foreground">
                                  {item.scope ? `${item.scope} · ` : ""}
                                  {item.source_path}
                                </span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </PanelTableWrap>
            {snapshot.capabilities.length === 0 ? <Empty what="capabilities" /> : null}
          </Panel>
        </TabsContent>

        <TabsContent value="mcp">
          <Panel>
            <PanelTableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>Server</TH>
                    <TH>Scope</TH>
                    <TH>Transport</TH>
                    <TH>Configured in</TH>
                  </TR>
                </THead>
                <TBody>
                  {snapshot.mcp_servers.map((server) => (
                    <TR key={`${server.scope}:${server.name}`}>
                      <TD>
                        <span className="font-medium">{server.name}</span>
                        <span className="block truncate font-mono text-xs text-muted-foreground">
                          {server.url ?? [server.command, ...server.args].filter(Boolean).join(" ")}
                        </span>
                        {server.auto_approved ? (
                          <Badge
                            variant="outline"
                            className="mt-1 rounded-full border-severity-medium/40 bg-severity-medium/10 px-2 py-0.5 text-severity-medium"
                          >
                            Auto-approved
                          </Badge>
                        ) : null}
                      </TD>
                      <TD>
                        <ScopeBadge scope={server.scope} />
                      </TD>
                      <TD className="text-muted-foreground">{server.transport}</TD>
                      <TD className="font-mono text-xs text-muted-foreground">{server.source_path}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </PanelTableWrap>
            {snapshot.mcp_servers.length === 0 ? <Empty what="MCP servers" /> : null}
          </Panel>
        </TabsContent>

        <TabsContent value="skills">
          <Panel>
            <PanelTableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>Skill</TH>
                    <TH>Scope</TH>
                    <TH>Source</TH>
                  </TR>
                </THead>
                <TBody>
                  {snapshot.skills.map((skill) => (
                    <TR key={skill.source_path}>
                      <TD>
                        <span className="font-medium">{skill.name}</span>
                        {skill.description ? (
                          <span className="block text-xs text-muted-foreground">{skill.description}</span>
                        ) : null}
                      </TD>
                      <TD>
                        <ScopeBadge scope={skill.scope} />
                      </TD>
                      <TD className="font-mono text-xs text-muted-foreground">{skill.source_path}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </PanelTableWrap>
            {snapshot.skills.length === 0 ? <Empty what="skills" /> : null}
          </Panel>
        </TabsContent>

        <TabsContent value="plugins">
          <Panel>
            <PanelTableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>Plugin</TH>
                    <TH>Source</TH>
                    <TH>Installed in</TH>
                  </TR>
                </THead>
                <TBody>
                  {snapshot.plugins.map((plugin) => (
                    <TR key={`${plugin.source}:${plugin.name}`}>
                      <TD className="font-medium">{plugin.name}</TD>
                      <TD className="text-muted-foreground">{plugin.source}</TD>
                      <TD className="font-mono text-xs text-muted-foreground">
                        {plugin.install_location ?? "unknown"}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </PanelTableWrap>
            {snapshot.plugins.length === 0 ? <Empty what="plugins" /> : null}
          </Panel>
        </TabsContent>

        <TabsContent value="hooks">
          <Panel>
            <PanelHeader>
              <PanelTitle>Hooks</PanelTitle>
              <PanelSubtitle>
                A hook runs a command on the agent&apos;s behalf, with the agent&apos;s privileges, whatever
                the permission rules say.
              </PanelSubtitle>
            </PanelHeader>
            <PanelTableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>Event</TH>
                    <TH>Matcher</TH>
                    <TH>Command</TH>
                    <TH>Scope</TH>
                  </TR>
                </THead>
                <TBody>
                  {snapshot.hooks.map((hook) => (
                    <TR key={`${hook.source_path}:${hook.event}:${hook.command}`}>
                      <TD className="font-medium">{hook.event}</TD>
                      <TD className="text-muted-foreground">{hook.matcher ?? "any"}</TD>
                      <TD className="font-mono text-xs">{hook.command}</TD>
                      <TD>
                        <ScopeBadge scope={hook.scope} />
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </PanelTableWrap>
            {snapshot.hooks.length === 0 ? <Empty what="hooks" /> : null}
          </Panel>
        </TabsContent>

        <TabsContent value="permissions">
          <Panel>
            <PanelHeader>
              <PanelTitle>Permission rules</PanelTitle>
              <PanelSubtitle>
                The rules exactly as written, beside the capabilities they produced. This is what you
                would edit to change any of it.
              </PanelSubtitle>
            </PanelHeader>
            <PanelTableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>Rule</TH>
                    <TH>Effect</TH>
                    <TH>Scope</TH>
                    <TH>Source</TH>
                  </TR>
                </THead>
                <TBody>
                  {snapshot.permissions.map((permission) => (
                    <TR key={`${permission.source_path}:${permission.effect}:${permission.rule}`}>
                      <TD className="font-mono text-xs">{permission.rule}</TD>
                      <TD
                        className={cn(
                          "font-medium",
                          permission.effect === "allow"
                            ? "text-severity-high"
                            : permission.effect === "deny"
                              ? "text-muted-foreground"
                              : "text-foreground",
                        )}
                      >
                        {permission.effect}
                      </TD>
                      <TD>
                        <ScopeBadge scope={permission.scope} />
                      </TD>
                      <TD className="font-mono text-xs text-muted-foreground">{permission.source_path}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </PanelTableWrap>
            {snapshot.permissions.length === 0 ? <Empty what="permission rules" /> : null}
          </Panel>
        </TabsContent>

        <TabsContent value="credentials">
          <Panel>
            <PanelHeader>
              <PanelTitle>Credentials in reach</PanelTitle>
              <PanelSubtitle>
                Presence and location only. The value is never read, never stored and never transmitted.
              </PanelSubtitle>
            </PanelHeader>
            <PanelTableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>Kind</TH>
                    <TH>Where</TH>
                    <TH>Present</TH>
                  </TR>
                </THead>
                <TBody>
                  {snapshot.credentials.map((credential) => (
                    <TR key={`${credential.source}:${credential.location}`}>
                      <TD className="font-medium">{credential.kind}</TD>
                      <TD className="font-mono text-xs text-muted-foreground">
                        {credential.source} · {credential.location}
                      </TD>
                      <TD>{credential.present ? "Yes" : "No"}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </PanelTableWrap>
            {snapshot.credentials.length === 0 ? <Empty what="credentials" /> : null}
          </Panel>
        </TabsContent>

        <TabsContent value="sources">
          <Panel>
            <PanelHeader>
              <PanelTitle>Configuration read</PanelTitle>
              <PanelSubtitle>
                Every file this report rests on, so the same conclusion can be reproduced.
              </PanelSubtitle>
            </PanelHeader>
            <PanelBody className="flex flex-col gap-4">
              <ul className="flex flex-col gap-1 font-mono text-xs">
                {snapshot.config_paths.map((path) => (
                  <li key={path}>{path}</li>
                ))}
              </ul>
              {snapshot.coverage.not_checked.length > 0 ? (
                <div>
                  <p className="subheader">Not checked</p>
                  <ul className="mt-1 flex flex-col gap-1 text-xs text-muted-foreground">
                    {snapshot.coverage.not_checked.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </PanelBody>
          </Panel>
        </TabsContent>
      </Tabs>
    </div>
  );
}
