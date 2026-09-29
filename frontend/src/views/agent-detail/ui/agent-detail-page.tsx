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
  CONFIDENCE_LABELS,
  describeCapability,
  describeRule,
  EFFECT_LABELS,
  RISK_LABELS,
  RISK_MEANINGS,
  RiskBadge,
  ScopeBadge,
} from "@/entities/agent";
import type { AgentDetail, CapabilityLevel, Permission } from "@/entities/agent";
import { workspaceAuthor } from "@/entities/organization";
import { ExplainButton } from "@/features/ai-explain";
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
  TechnicalDetails,
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

const EFFECT_CLASSES: Record<Permission["effect"], string> = {
  allow: "text-severity-high",
  ask: "text-foreground",
  deny: "text-muted-foreground",
};

function Empty({ what }: { what: string }) {
  return <EmptyState title={`No ${what} found`} body={`This agent did not report any ${what}.`} />;
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
        if (!cancelled) setError(err instanceof ApiError ? err.message : "We could not load this agent.");
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
          <AlertTitle>We could not load this agent</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading this agent">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const snapshot = agent.snapshot;
  const deductions = agent.risk_factors.filter((factor) => factor.points > 0);

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
            Last checked {formatDateTime(agent.reported_at)}
            {workspaceAuthor(agent) ? ` by ${workspaceAuthor(agent)}` : ""}.
          </>
        }
        actions={
          <span className="flex items-center gap-3">
            <span className="text-lg font-semibold tabular-nums">{agent.posture_score}/100</span>
            <RiskBadge risk={agent.risk} />
          </span>
        }
      />

      {/* Is it safe, why, and what to do: answered before any table. The
          plain sentences come from the scanner beside each technical reason,
          so the two cannot disagree, and the reasons stay one click away. */}
      <Panel>
        <PanelHeader>
          <PanelTitle>How safe is this agent?</PanelTitle>
        </PanelHeader>
        <PanelBody className="flex flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <p className="text-base font-medium">
              {RISK_LABELS[agent.risk]} risk. {RISK_MEANINGS[agent.risk]}
            </p>
            <p className="text-sm text-muted-foreground">
              Safety score <strong className="text-foreground tabular-nums">{agent.posture_score} out of 100</strong>.
              Higher is safer. It starts at 100 and loses points for each thing below.{" "}
              {CONFIDENCE_LABELS[agent.confidence]}.
            </p>
          </div>

          <div>
            <p className="text-sm font-medium">Why it got this score</p>
            <ul className="mt-2 flex flex-col gap-2">
              {agent.risk_factors.map((factor) => (
                <li key={factor.reason} className="flex gap-3 text-sm">
                  <span className="w-16 shrink-0 text-right text-xs text-muted-foreground tabular-nums">
                    {factor.points ? `-${factor.points} points` : "No points lost"}
                  </span>
                  <span>{factor.plain || factor.reason}</span>
                </li>
              ))}
            </ul>
          </div>

          {deductions.length > 0 ? (
            <div>
              <p className="text-sm font-medium">What should I do?</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Take away access this agent does not need. Each kind of access is listed under{" "}
                <em>What it can reach</em>, and the rules that give it are under <em>Rules</em>: change
                those rules, then run <code className="font-mono text-[13px]">aevrin agent scan --upload</code>{" "}
                again to see the new score.
              </p>
            </div>
          ) : null}

          <ExplainButton
            subjectType="agent_posture"
            subjectId={agent.id}
            label={`Why is this agent ${RISK_LABELS[agent.risk].toLowerCase()} risk?`}
            className="w-fit"
          />

          <TechnicalDetails>
            <p>
              Agent posture score: {agent.posture_score}/100, risk {agent.risk}, confidence {agent.confidence}.
              How much this agent can already do on this machine. This is not an MCP server&apos;s
              scan score or trust grade, which say whether one server is safe to run.
            </p>
            <ul className="flex flex-col gap-1">
              {agent.risk_factors.map((factor) => (
                <li key={factor.reason} className="font-mono">
                  {factor.points ? `-${factor.points}` : "0"} {factor.reason}
                </li>
              ))}
            </ul>
          </TechnicalDetails>
        </PanelBody>
      </Panel>

      {/* Reads the normalised flag, not a vendor string: Claude Code spells
          this `bypassPermissions` and Codex spells it `approval_policy =
          never`, and the page should not have to know either. */}
      {snapshot.unattended ? (
        <Alert variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>This agent does not ask you before it acts</AlertTitle>
          <AlertDescription>
            <p>
              Nobody gets a chance to say no before it does something. This does not give it more
              access, but it takes away the check on all the access it already has.
            </p>
            <TechnicalDetails className="mt-2">
              <p>
                Permission mode: <code className="font-mono">{snapshot.default_permission_mode}</code>. No
                action is put to a human before it runs.
              </p>
            </TechnicalDetails>
          </AlertDescription>
        </Alert>
      ) : null}

      {!agent.coverage_complete ? (
        <Alert>
          <AlertTitle>We could not read all of this agent&apos;s settings</AlertTitle>
          <AlertDescription>
            <p>
              So this report is not complete. Anything we could not read is counted as the most it
              could allow, never as safe.
            </p>
            {snapshot.unreadable_paths.length > 0 ? (
              <TechnicalDetails className="mt-2" label="Files we could not read">
                <p className="font-mono">{snapshot.unreadable_paths.join(", ")}</p>
              </TechnicalDetails>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : null}

      <Tabs defaultValue="capabilities">
        {/* Eight tabs do not fit a phone. The row scrolls on its own so the
            page itself never scrolls sideways. */}
        <div className="max-w-full overflow-x-auto">
          <TabsList>
            <TabsTrigger value="capabilities">What it can reach</TabsTrigger>
            <TabsTrigger value="permissions">Rules ({agent.permissions.length})</TabsTrigger>
            <TabsTrigger value="mcp">MCP servers ({snapshot.mcp_servers.length})</TabsTrigger>
            <TabsTrigger value="skills">Skills ({snapshot.skills.length})</TabsTrigger>
            <TabsTrigger value="plugins">Plugins ({snapshot.plugins.length})</TabsTrigger>
            <TabsTrigger value="hooks">Hooks ({snapshot.hooks.length})</TabsTrigger>
            <TabsTrigger value="credentials">Passwords and keys ({snapshot.credentials.length})</TabsTrigger>
            <TabsTrigger value="sources">Files we read</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="capabilities">
          <Panel>
            <PanelHeader className="flex-col items-start gap-1">
              <PanelTitle>What this agent can reach</PanelTitle>
              <PanelSubtitle>
                The most access this agent gets from any of its settings files. A setting can allow
                something in one file and not in another; this shows the widest, because that is how
                far the agent could go. It does not mean all of it is switched on at once.
              </PanelSubtitle>
              <TechnicalDetails>
                <p>
                  Effective capabilities: the widest grant across every configuration file, not the
                  winner of precedence. Precedence decides which setting applies; it does not narrow
                  what the agent can reach.
                </p>
              </TechnicalDetails>
            </PanelHeader>
            <PanelTableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>What it can do</TH>
                    <TH>How much</TH>
                    <TH>Rules that allow it</TH>
                  </TR>
                </THead>
                <TBody>
                  {snapshot.capabilities.map((capability) => (
                    <TR key={`${capability.capability}:${capability.subject ?? ""}`}>
                      <TD className="min-w-56 align-top">
                        <span className="font-medium">
                          {CAPABILITY_LABELS[capability.capability]}
                          {capability.subject ? `: ${capability.subject}` : ""}
                        </span>
                        <span className="mt-0.5 block text-xs text-muted-foreground">
                          {describeCapability(capability)}
                        </span>
                      </TD>
                      <TD className={cn("align-top font-medium", LEVEL_CLASSES[capability.level])}>
                        {CAPABILITY_LEVEL_LABELS[capability.level]}
                      </TD>
                      <TD className="align-top">
                        {capability.evidence.length === 0 ? (
                          <span className="text-xs text-muted-foreground">No rule gave this.</span>
                        ) : (
                          <ul className="flex flex-col gap-1.5">
                            {capability.evidence.map((item) => (
                              <li key={`${item.source_path}:${item.detail}`} className="text-xs">
                                <span className="font-mono">{item.detail}</span>
                                <span className="block text-muted-foreground">
                                  {item.scope ? <ScopeBadge scope={item.scope} className="mr-1.5" /> : null}
                                  <span className="font-mono">{item.source_path}</span>
                                </span>
                              </li>
                            ))}
                          </ul>
                        )}
                        <TechnicalDetails className="mt-1.5">
                          <p>
                            Capability <code className="font-mono">{capability.capability}</code>, level{" "}
                            <code className="font-mono">{capability.level}</code>
                            {capability.subject ? (
                              <>
                                , server <code className="font-mono">{capability.subject}</code>
                              </>
                            ) : null}
                            .
                          </p>
                        </TechnicalDetails>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </PanelTableWrap>
            {snapshot.capabilities.length === 0 ? <Empty what="access" /> : null}
          </Panel>
        </TabsContent>

        <TabsContent value="permissions">
          <Panel>
            <PanelHeader className="flex-col items-start gap-1">
              <PanelTitle>Rules that give this agent access</PanelTitle>
              <PanelSubtitle>
                The rules written in this agent&apos;s settings, and what each one does. They are why the
                agent has the access under <em>What it can reach</em>. To change what it can reach,
                change these rules.
              </PanelSubtitle>
              <TechnicalDetails>
                <p>
                  Permission rules exactly as written, beside the capabilities they produced. This is
                  what you would edit to change any of it.
                </p>
              </TechnicalDetails>
            </PanelHeader>
            <RulesTable permissions={agent.permissions} />
            {agent.permissions.length === 0 ? <Empty what="rules" /> : null}
          </Panel>
        </TabsContent>

        <TabsContent value="mcp">
          <Panel>
            <PanelHeader className="flex-col items-start gap-1">
              <PanelTitle>MCP servers</PanelTitle>
              <PanelSubtitle>
                An MCP server is an add-on that gives the agent extra tools. These are the ones this
                agent is set up to use.
              </PanelSubtitle>
            </PanelHeader>
            <PanelTableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>Server</TH>
                    <TH>Where it is set</TH>
                    <TH>How it connects</TH>
                    <TH>Settings file</TH>
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
                            Used without asking you
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
            <PanelHeader className="flex-col items-start gap-1">
              <PanelTitle>Skills</PanelTitle>
              <PanelSubtitle>Saved instructions this agent can follow.</PanelSubtitle>
            </PanelHeader>
            <PanelTableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>Skill</TH>
                    <TH>Where it is set</TH>
                    <TH>File</TH>
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
            <PanelHeader className="flex-col items-start gap-1">
              <PanelTitle>Plugins</PanelTitle>
              <PanelSubtitle>Add-ons installed into this agent.</PanelSubtitle>
            </PanelHeader>
            <PanelTableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>Plugin</TH>
                    <TH>From</TH>
                    <TH>Installed in</TH>
                  </TR>
                </THead>
                <TBody>
                  {snapshot.plugins.map((plugin) => (
                    <TR key={`${plugin.source}:${plugin.name}`}>
                      <TD className="font-medium">{plugin.name}</TD>
                      <TD className="text-muted-foreground">{plugin.source}</TD>
                      <TD className="font-mono text-xs text-muted-foreground">
                        {plugin.install_location ?? "Not known"}
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
            <PanelHeader className="flex-col items-start gap-1">
              <PanelTitle>Hooks</PanelTitle>
              <PanelSubtitle>
                A hook is a command that runs by itself when the agent does something. It runs with all
                of the agent&apos;s access, whatever the rules say.
              </PanelSubtitle>
            </PanelHeader>
            <PanelTableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>When it runs</TH>
                    <TH>For</TH>
                    <TH>Command</TH>
                    <TH>Where it is set</TH>
                  </TR>
                </THead>
                <TBody>
                  {snapshot.hooks.map((hook) => (
                    <TR key={`${hook.source_path}:${hook.event}:${hook.command}`}>
                      <TD className="font-medium">{hook.event}</TD>
                      <TD className="text-muted-foreground">{hook.matcher ?? "Everything"}</TD>
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

        <TabsContent value="credentials">
          <Panel>
            <PanelHeader className="flex-col items-start gap-1">
              <PanelTitle>Passwords and keys it can reach</PanelTitle>
              <PanelSubtitle>
                We only check whether each one is there, and where. We never read, save or send the
                password or key itself.
              </PanelSubtitle>
            </PanelHeader>
            <PanelTableWrap>
              <Table>
                <THead>
                  <TR>
                    <TH>What it is</TH>
                    <TH>Where</TH>
                    <TH>Is it there?</TH>
                  </TR>
                </THead>
                <TBody>
                  {snapshot.credentials.map((credential) => (
                    <TR key={`${credential.source}:${credential.location}`}>
                      <TD className="font-medium">{credential.kind.replace(/_/g, " ")}</TD>
                      <TD className="font-mono text-xs text-muted-foreground">
                        {credential.source} · {credential.location}
                      </TD>
                      <TD>{credential.present ? "Yes" : "No"}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </PanelTableWrap>
            {snapshot.credentials.length === 0 ? <Empty what="passwords or keys" /> : null}
          </Panel>
        </TabsContent>

        <TabsContent value="sources">
          <Panel>
            <PanelHeader className="flex-col items-start gap-1">
              <PanelTitle>Files we read</PanelTitle>
              <PanelSubtitle>
                Every settings file this report is based on, so anyone can check it and get the same
                answer.
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
                  <p className="text-sm font-medium">What we could not check</p>
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

/** Rule, what it does, exactly as written: the order a reader needs them. */
function RulesTable({ permissions }: { permissions: Permission[] }) {
  return (
    <PanelTableWrap>
      <Table>
        <THead>
          <TR>
            <TH>What it does</TH>
            <TH>Rule, exactly as written</TH>
            <TH>Effect</TH>
            <TH>Where it is set</TH>
          </TR>
        </THead>
        <TBody>
          {permissions.map((permission) => (
            <TR key={`${permission.source_path}:${permission.effect}:${permission.rule}`}>
              <TD className="min-w-64 align-top text-sm">{describeRule(permission)}</TD>
              <TD className="align-top font-mono text-xs">{permission.rule}</TD>
              <TD className={cn("align-top font-medium", EFFECT_CLASSES[permission.effect])}>
                {EFFECT_LABELS[permission.effect]}
              </TD>
              <TD className="align-top">
                <ScopeBadge scope={permission.scope} />
                <span className="mt-1 block font-mono text-xs text-muted-foreground">{permission.source_path}</span>
                <TechnicalDetails className="mt-1.5">
                  <p>
                    Effect <code className="font-mono">{permission.effect}</code>
                    {permission.grants.length > 0 ? (
                      <>
                        ; evidence for{" "}
                        {permission.grants.map((grant) => (
                          <code key={`${grant.capability}:${grant.subject ?? ""}`} className="mr-1 font-mono">
                            {grant.capability}
                            {grant.subject ? `:${grant.subject}` : ""}
                          </code>
                        ))}
                      </>
                    ) : null}
                    .
                  </p>
                </TechnicalDetails>
              </TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </PanelTableWrap>
  );
}
