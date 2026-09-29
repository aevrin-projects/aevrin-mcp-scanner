"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { ApiError } from "@/shared/api";
import { agentApi, AGENT_KIND_LABELS, describeRule, EFFECT_LABELS, ScopeBadge } from "@/entities/agent";
import type { Permission } from "@/entities/agent";
import {
  EmptyState,
  PageHeader,
  Panel,
  PanelBody,
  PanelTableWrap,
  TechnicalDetails,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
} from "@/shared/ui";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Input } from "@/shared/ui/input";
import { Select } from "@/shared/ui/select";
import { Skeleton } from "@/shared/ui/skeleton";
import { cn } from "@/shared/lib/utils";

const EFFECT_CLASSES: Record<Permission["effect"], string> = {
  allow: "text-severity-high",
  ask: "text-foreground",
  deny: "text-muted-foreground",
};

export function PermissionsPage() {
  const [permissions, setPermissions] = useState<Permission[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [effect, setEffect] = useState<Permission["effect"] | "all">("all");

  useEffect(() => {
    let cancelled = false;
    agentApi
      .listPermissions()
      .then((result) => {
        if (!cancelled) setPermissions(result);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "We could not load your rules.");
        setPermissions([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (permissions ?? []).filter((permission) => {
      if (effect !== "all" && permission.effect !== effect) return false;
      if (!needle) return true;
      return [permission.rule, permission.hostname, permission.source_path].some((field) =>
        field.toLowerCase().includes(needle),
      );
    });
  }, [permissions, query, effect]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        pretitle="AI security"
        title="Rules"
        description="Every rule that gives your agents access, on every computer, with what it does and the file it is written in."
      />

      {/* The line the person actually typed, which is what they need to change
          it, beside what it does. What the rules add up to per agent is on the
          agent's "What it can reach" tab. */}
      <Alert>
        <AlertTitle>A rule is what you change</AlertTitle>
        <AlertDescription>
          <p>
            Each rule is shown exactly as it is written in the settings file, next to what it does. To
            change what an agent can reach, change its rules. To see everything one agent can reach,
            open the agent.
          </p>
          <TechnicalDetails className="mt-2">
            <p>
              Rules as written. An agent&apos;s effective access is the widest grant across every file,
              not the winner of precedence.
            </p>
          </TechnicalDetails>
        </AlertDescription>
      </Alert>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>We could not load your rules</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {permissions === null ? (
        <Panel>
          <PanelBody className="flex flex-col gap-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </PanelBody>
        </Panel>
      ) : permissions.length === 0 && !error ? (
        <Panel>
          <EmptyState
            icon={<ShieldCheck />}
            title="No rules yet"
            body="Rules show up here after a computer with an agent that has rules is checked."
          />
        </Panel>
      ) : permissions.length === 0 ? null : (
        <Panel>
          <PanelBody className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search rules, computers or files"
              aria-label="Search rules"
              className="sm:max-w-xs"
            />
            <Select
              value={effect}
              onChange={(event) => setEffect(event.target.value as Permission["effect"] | "all")}
              aria-label="Filter by what the rule does"
              className="sm:max-w-[200px]"
            >
              <option value="all">All rules</option>
              <option value="allow">{EFFECT_LABELS.allow}</option>
              <option value="ask">{EFFECT_LABELS.ask}</option>
              <option value="deny">{EFFECT_LABELS.deny}</option>
            </Select>
          </PanelBody>
          <PanelTableWrap>
            <Table>
              <THead>
                <TR>
                  <TH>What it does</TH>
                  <TH>Rule, exactly as written</TH>
                  <TH>Effect</TH>
                  <TH>Where it is set</TH>
                  <TH>Agent</TH>
                  <TH>Computer</TH>
                  <TH>File</TH>
                </TR>
              </THead>
              <TBody>
                {visible.map((permission, index) => (
                  <TR key={`${permission.agent_id}:${permission.source_path}:${permission.rule}:${index}`}>
                    <TD className="min-w-64 text-sm">{describeRule(permission)}</TD>
                    <TD className="font-mono text-xs">{permission.rule}</TD>
                    <TD className={cn("font-medium", EFFECT_CLASSES[permission.effect])}>
                      {EFFECT_LABELS[permission.effect]}
                    </TD>
                    <TD>
                      <ScopeBadge scope={permission.scope} />
                    </TD>
                    <TD>
                      <Link href={`/agents/${permission.agent_id}`} className="hover:underline">
                        {AGENT_KIND_LABELS[permission.agent_type]}
                      </Link>
                    </TD>
                    <TD className="text-muted-foreground">{permission.hostname}</TD>
                    <TD className="truncate font-mono text-xs text-muted-foreground">
                      {permission.source_path}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </PanelTableWrap>
          {visible.length === 0 ? <EmptyState title="No rules match this search" /> : null}
        </Panel>
      )}
    </div>
  );
}
