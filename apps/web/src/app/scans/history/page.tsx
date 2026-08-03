"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { api } from "@/lib/api";
import type { Finding, Scan, ScanStage, ScanStatus, TargetType } from "@/lib/types";
import { PageHeader, SectionCard } from "@/components/product-ui";
import { StatusBadge } from "@/components/status-badge";
import { SeverityBadge } from "@/components/severity-badge";
import { Input } from "@/components/ui/input";
import { TARGET_TYPE_LABELS, formatDateTime, formatDuration, summarizeFindings } from "@/lib/presentation";
import { Skeleton } from "@/components/ui/skeleton";

type Summary = { scan: Scan; findings: Finding[]; stages: ScanStage[] };

export default function ScanHistoryPage() {
  const [summaries, setSummaries] = useState<Summary[] | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<ScanStatus | "all">("all");
  const [targetTypeFilter, setTargetTypeFilter] = useState<TargetType | "all">("all");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const scans = await api.listScans();
      const details = await Promise.all(
        scans.map(async (scan) => {
          const [findings, stages] = await Promise.all([
            api.getScanFindings(scan.id).catch(() => []),
            api.getScanStages(scan.id).catch(() => []),
          ]);
          return { scan, findings, stages };
        }),
      );
      if (!cancelled) setSummaries(details);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    if (!summaries) return [];
    return summaries.filter((summary) => {
      if (statusFilter !== "all" && summary.scan.status !== statusFilter) return false;
      if (targetTypeFilter !== "all" && summary.scan.target_type !== targetTypeFilter) return false;
      if (query && !summary.scan.target.toLowerCase().includes(query.toLowerCase())) return false;
      return true;
    });
  }, [query, statusFilter, summaries, targetTypeFilter]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Scan history"
        description="Search by target, filter by completion state or target type, and review what coverage and severity each scan actually produced."
        actions={
          <Link href="/scans/new">
            <button className="inline-flex h-8 items-center rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground">
              New scan
            </button>
          </Link>
        }
      />

      <SectionCard
        title="Filters"
        description="Comparison is only meaningful between repeated scans of the same target, so this view keeps the raw rows visible."
      >
        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px_220px]">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(event) => setQuery(event.target.value)} className="pl-9" placeholder="Search by repository or server URL" />
          </div>
          <select
            className="h-9 rounded-lg border border-border bg-background px-3 text-sm"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as ScanStatus | "all")}
          >
            <option value="all">All statuses</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
            <option value="completed">Complete</option>
            <option value="incomplete">Partial</option>
            <option value="failed">Failed</option>
          </select>
          <select
            className="h-9 rounded-lg border border-border bg-background px-3 text-sm"
            value={targetTypeFilter}
            onChange={(event) => setTargetTypeFilter(event.target.value as TargetType | "all")}
          >
            <option value="all">All target types</option>
            <option value="github_repo">GitHub repository</option>
            <option value="live_mcp_server">Live MCP server</option>
            <option value="config_paste">Pasted configuration</option>
          </select>
        </div>
      </SectionCard>

      <SectionCard title="Scans" description={`${filtered.length} visible scan${filtered.length === 1 ? "" : "s"}.`}>
        <div className="space-y-3">
          {summaries === null
            ? Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-32 rounded-2xl" />)
            : filtered.map((summary) => (
                <ScanHistoryRow key={summary.scan.id} summary={summary} />
              ))}
        </div>
      </SectionCard>
    </div>
  );
}

function ScanHistoryRow({ summary }: { summary: Summary }) {
  const counts = summarizeFindings(summary.findings.filter((finding) => !finding.not_tested && finding.triage_status === "open"));

  return (
    <Link
      href={`/scans/${summary.scan.id}`}
      className="grid gap-4 rounded-2xl border border-border bg-background/80 p-4 transition-colors hover:bg-muted/30 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto]"
    >
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={summary.scan.status} />
          <span className="text-sm text-muted-foreground">{TARGET_TYPE_LABELS[summary.scan.target_type]}</span>
        </div>
        <div className="break-all text-base font-medium">{summary.scan.target}</div>
      </div>

      <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
        <span>Finished: {formatDateTime(summary.scan.completed_at ?? summary.scan.created_at)}</span>
        <span>Duration: {formatDuration(summary.scan.created_at, summary.scan.completed_at)}</span>
        <span>Critical: {counts.critical}</span>
        <span>High: {counts.high}</span>
      </div>

      <div className="flex items-center gap-2">
        <div className="flex flex-col items-end gap-1">
          {counts.critical > 0 ? <SeverityBadge severity="critical" /> : null}
          {counts.high > 0 ? <SeverityBadge severity="high" /> : null}
          {counts.critical === 0 && counts.high === 0 ? (
            <span className="text-xs text-muted-foreground">No critical or high findings</span>
          ) : null}
        </div>
      </div>
    </Link>
  );
}
