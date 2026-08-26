"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Blocks, ChevronRight, ScanSearch } from "lucide-react";
import { ApiError } from "@/shared/api";
import {
  agentApi,
  AGENT_KIND_LABELS,
  PolicyBadge,
  ScopeBadge,
  SCOPE_LABELS,
  TrustGradeBadge,
} from "@/entities/agent";
import type { ConfigScope, McpAsset } from "@/entities/agent";
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
import { formatDateTime } from "@/shared/lib/format";

const SCOPES: ConfigScope[] = ["managed", "user", "project", "local"];

/** A stdio server is a command on someone's machine, so there is nothing the
 *  dashboard can reach. An http server has a URL and can be scanned now. */
function scanHref(asset: McpAsset) {
  return asset.url ? `/scans/new?mode=live_mcp_server&target=${encodeURIComponent(asset.url)}` : null;
}

function InstallationList({ asset }: { asset: McpAsset }) {
  return (
    <ul className="flex flex-col gap-2">
      {asset.installations.map((installation) => (
        <li
          key={`${installation.agent_id}:${installation.source_path}:${installation.name}`}
          className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"
        >
          <ScopeBadge scope={installation.scope} />
          <Link href={`/agents/${installation.agent_id}`} className="font-medium hover:underline">
            {AGENT_KIND_LABELS[installation.agent_type] ?? installation.agent_name}
          </Link>
          <span className="text-muted-foreground">on {installation.hostname}</span>
          {installation.project_root ? (
            <span className="truncate text-muted-foreground">· {installation.project_root}</span>
          ) : null}
          {installation.name !== asset.name ? (
            <span className="text-muted-foreground">· named &ldquo;{installation.name}&rdquo;</span>
          ) : null}
          {!installation.enabled ? <span className="text-muted-foreground">· disabled</span> : null}
          {installation.auto_approved ? (
            <span className="text-severity-medium">· auto-approved</span>
          ) : null}
          <span className="text-muted-foreground">· {formatDateTime(installation.reported_at)}</span>
        </li>
      ))}
    </ul>
  );
}

export function McpInventoryPage() {
  const [assets, setAssets] = useState<McpAsset[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<ConfigScope | "all">("all");
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    agentApi
      .listMcpServers()
      .then((result) => {
        if (cancelled) return;
        setAssets(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load your MCP servers.");
        setAssets([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (assets ?? []).filter((asset) => {
      if (scope !== "all" && !asset.scopes.includes(scope)) return false;
      if (!needle) return true;
      return [
        asset.name,
        asset.identity_label,
        asset.command ?? "",
        asset.url ?? "",
        ...asset.installations.map((i) => i.hostname),
      ].some((field) => field.toLowerCase().includes(needle));
    });
  }, [assets, query, scope]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        pretitle="AI security"
        title="MCP servers"
        description="One row per server, however many agents and devices it is configured on."
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

      {assets === null ? (
        <Panel>
          <PanelBody className="flex flex-col gap-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </PanelBody>
        </Panel>
      ) : assets.length === 0 && !error ? (
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
      ) : assets.length === 0 ? null : (
        <Panel>
          <PanelBody className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by name, package, URL or device"
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
                  <TH>Trust</TH>
                  <TH>Installed</TH>
                  <TH>Transport</TH>
                  <TH className="text-right">Scan</TH>
                </TR>
              </THead>
              <TBody>
                {visible.map((asset) => {
                  const href = scanHref(asset);
                  const open = expanded === asset.identity_key;
                  return (
                    <TR key={asset.identity_key}>
                      <TD>
                        <button
                          type="button"
                          onClick={() => setExpanded(open ? null : asset.identity_key)}
                          aria-expanded={open}
                          className="flex items-center gap-1 text-left font-medium hover:underline"
                        >
                          {asset.name}
                          <ChevronRight
                            className={`size-3.5 text-muted-foreground transition-transform ${open ? "rotate-90" : ""}`}
                            aria-hidden="true"
                          />
                        </button>
                        <span className="block truncate font-mono text-xs text-muted-foreground">
                          {asset.identity_label}
                        </span>
                        {/* Correlation is only as good as what the config pins
                            down. Saying so beats a confident-looking row that
                            merged two unrelated servers. */}
                        {asset.identity_confidence === "low" ? (
                          <Badge
                            variant="outline"
                            className="mt-1 rounded-full px-2 py-0.5 text-muted-foreground"
                            title="Identified only by the name someone typed, so it is never merged with any other server."
                          >
                            Identity uncertain
                          </Badge>
                        ) : null}
                        {open ? (
                          <div className="mt-3 border-l-2 border-border pl-3">
                            <InstallationList asset={asset} />
                          </div>
                        ) : null}
                      </TD>
                      <TD>
                        {/* Never a letter without a scan behind it. */}
                        {asset.trust ? (
                          <Link href={`/scans/${asset.trust.scan_id}`} className="inline-block">
                            <TrustGradeBadge
                              grade={asset.trust.grade}
                              label={asset.trust.label}
                              score={asset.trust.scan_score}
                            />
                          </Link>
                        ) : (
                          <span className="text-xs text-muted-foreground">Not scanned</span>
                        )}
                        {/* Only rendered when a policy is switched on. */}
                        <PolicyBadge policy={asset.policy} className="mt-1" />
                      </TD>
                      <TD>
                        <span className="flex flex-wrap gap-1">
                          {asset.scopes.map((value) => (
                            <ScopeBadge key={value} scope={value} />
                          ))}
                        </span>
                        <span className="mt-1 block text-xs text-muted-foreground">
                          {asset.device_count} device{asset.device_count === 1 ? "" : "s"} ·{" "}
                          {asset.agent_count} agent{asset.agent_count === 1 ? "" : "s"}
                          {asset.enabled_everywhere ? "" : " · disabled somewhere"}
                        </span>
                      </TD>
                      <TD className="text-muted-foreground">{asset.transport}</TD>
                      <TD className="text-right">
                        {href ? (
                          <Button nativeButton={false} render={<Link href={href} />} variant="outline" size="sm">
                            <ScanSearch className="size-4" />
                            Scan
                          </Button>
                        ) : (
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
