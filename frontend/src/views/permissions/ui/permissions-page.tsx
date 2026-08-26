"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { ApiError } from "@/shared/api";
import { agentApi, AGENT_KIND_LABELS, ScopeBadge } from "@/entities/agent";
import type { Permission } from "@/entities/agent";
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
        setError(err instanceof ApiError ? err.message : "Could not load your permission rules.");
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
        title="Permissions"
        description="Every rule across every device, exactly as written, with the file it lives in."
      />

      {/* The normalised capability is on the agent page. This is the line the
          person actually typed, which is what they need to change it. */}
      <Alert>
        <AlertTitle>Rules, not conclusions</AlertTitle>
        <AlertDescription>
          These are the rules as written. What each one adds up to is on the agent&apos;s
          Capabilities tab, where effective access is the widest grant across every file rather than
          the winner of precedence.
        </AlertDescription>
      </Alert>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load permissions</AlertTitle>
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
            title="No permission rules reported"
            body="Rules appear here once a device with them reports in."
          />
        </Panel>
      ) : permissions.length === 0 ? null : (
        <Panel>
          <PanelBody className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search rules, devices or files"
              aria-label="Search permission rules"
              className="sm:max-w-xs"
            />
            <Select
              value={effect}
              onChange={(event) => setEffect(event.target.value as Permission["effect"] | "all")}
              aria-label="Filter by effect"
              className="sm:max-w-[180px]"
            >
              <option value="all">All effects</option>
              <option value="allow">Allow</option>
              <option value="ask">Ask</option>
              <option value="deny">Deny</option>
            </Select>
          </PanelBody>
          <PanelTableWrap>
            <Table>
              <THead>
                <TR>
                  <TH>Rule</TH>
                  <TH>Effect</TH>
                  <TH>Scope</TH>
                  <TH>Agent</TH>
                  <TH>Device</TH>
                  <TH>File</TH>
                </TR>
              </THead>
              <TBody>
                {visible.map((permission, index) => (
                  <TR key={`${permission.agent_id}:${permission.source_path}:${permission.rule}:${index}`}>
                    <TD className="font-mono text-xs">{permission.rule}</TD>
                    <TD className={cn("font-medium", EFFECT_CLASSES[permission.effect])}>
                      {permission.effect}
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
          {visible.length === 0 ? <EmptyState title="No rules match this filter" /> : null}
        </Panel>
      )}
    </div>
  );
}
