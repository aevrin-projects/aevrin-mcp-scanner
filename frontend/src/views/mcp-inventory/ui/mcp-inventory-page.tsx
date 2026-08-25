"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Blocks, ScanSearch } from "lucide-react";
import { ApiError } from "@/shared/api";
import { agentApi, AGENT_KIND_LABELS, ScopeBadge, SCOPE_LABELS } from "@/entities/agent";
import type { ConfigScope, McpServerInventoryItem } from "@/entities/agent";
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
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Select } from "@/shared/ui/select";
import { Skeleton } from "@/shared/ui/skeleton";

const SCOPES: ConfigScope[] = ["managed", "user", "project", "local"];

/** Where a server can be scanned from, given what its configuration says.
 *  A stdio server is a command on a machine, so there is nothing the
 *  dashboard can reach; an http server has a URL and can be scanned now. */
function scanHref(server: McpServerInventoryItem) {
  if (server.url) {
    return `/scans/new?mode=live_mcp_server&target=${encodeURIComponent(server.url)}`;
  }
  return null;
}

export function McpInventoryPage() {
  const [servers, setServers] = useState<McpServerInventoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<ConfigScope | "all">("all");

  const load = useCallback(() => {
    let cancelled = false;
    agentApi
      .listMcpServers()
      .then((result) => {
        if (cancelled) return;
        setServers(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load your MCP servers.");
        setServers([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (servers ?? []).filter((server) => {
      if (scope !== "all" && server.scope !== scope) return false;
      if (!needle) return true;
      return [server.name, server.hostname, server.command ?? "", server.url ?? ""].some((field) =>
        field.toLowerCase().includes(needle),
      );
    });
  }, [servers, query, scope]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        pretitle="AI security"
        title="MCP servers"
        description="Every MCP server configured on a device that has reported in, and the scope it was configured at."
      />

      <Alert>
        <AlertTitle>Read-only</AlertTitle>
        <AlertDescription>
          These are the servers your agents are configured to load. Adding, removing or disabling one
          happens on the machine itself; Aevrin cannot change a configuration from here.
        </AlertDescription>
      </Alert>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load MCP servers</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {servers === null ? (
        <Panel>
          <PanelBody className="flex flex-col gap-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </PanelBody>
        </Panel>
      ) : servers.length === 0 && !error ? (
        <Panel>
          <EmptyState
            icon={<Blocks />}
            title="No MCP servers reported"
            body="Once a device reports in, every MCP server its agents are configured to load appears here."
            action={
              <Button nativeButton={false} render={<Link href="/agents" />} variant="outline" size="sm">
                How to report a device
              </Button>
            }
          />
        </Panel>
      ) : servers.length === 0 ? null : (
        <Panel>
          <PanelBody className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by name, device or command"
              aria-label="Search MCP servers"
              className="sm:max-w-xs"
            />
            <Select
              value={scope}
              onChange={(event) => setScope(event.target.value as ConfigScope | "all")}
              aria-label="Filter by scope"
              className="sm:max-w-[200px]"
            >
              <option value="all">All scopes</option>
              {SCOPES.map((value) => (
                <option key={value} value={value}>
                  {SCOPE_LABELS[value]}
                </option>
              ))}
            </Select>
          </PanelBody>
          <PanelTableWrap>
            <Table>
              <THead>
                <TR>
                  <TH>Server</TH>
                  <TH>Scope</TH>
                  <TH>Transport</TH>
                  <TH>Agent</TH>
                  <TH>Device</TH>
                  <TH className="text-right">Scan</TH>
                </TR>
              </THead>
              <TBody>
                {visible.map((server) => {
                  const href = scanHref(server);
                  return (
                    <TR key={`${server.agent_id}:${server.scope}:${server.name}`}>
                      <TD>
                        <span className="font-medium">{server.name}</span>
                        <span className="block truncate font-mono text-xs text-muted-foreground">
                          {server.url ?? server.command ?? server.source_path}
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
                        {server.scope === "project" && server.project_root ? (
                          <span className="block truncate text-xs text-muted-foreground">
                            {server.project_root}
                          </span>
                        ) : null}
                      </TD>
                      <TD className="text-muted-foreground">{server.transport}</TD>
                      <TD>
                        <Link href={`/agents/${server.agent_id}`} className="hover:underline">
                          {AGENT_KIND_LABELS[server.agent_type] ?? server.agent_name}
                        </Link>
                      </TD>
                      <TD className="text-muted-foreground">{server.hostname}</TD>
                      <TD className="text-right">
                        {href ? (
                          <Button nativeButton={false} render={<Link href={href} />} variant="outline" size="sm">
                            <ScanSearch className="size-4" />
                            Scan
                          </Button>
                        ) : (
                          // A stdio server is a command that runs on that
                          // machine. There is no URL for the dashboard to
                          // reach, and offering a button that cannot work
                          // would be the lie this product cannot afford.
                          <span className="text-xs text-muted-foreground">Local command</span>
                        )}
                      </TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
          </PanelTableWrap>
          {visible.length === 0 ? (
            <EmptyState title="No servers match this filter" body="Try a different scope or search term." />
          ) : null}
        </Panel>
      )}
    </div>
  );
}
