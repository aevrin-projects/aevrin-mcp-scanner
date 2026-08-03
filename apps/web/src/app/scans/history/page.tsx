"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { Finding, Scan, ScanStage, ScanStatus, TargetType } from "@/lib/types";
import { EmptyState, PageHeader, SectionCard } from "@/components/product-ui";
import { StatusBadge } from "@/components/status-badge";
import { SeverityBadge } from "@/components/severity-badge";
import { Input } from "@/components/ui/input";
import { SCAN_SOURCE_LABELS, TARGET_TYPE_LABELS, formatDateTime, formatDuration, summarizeFindings } from "@/lib/presentation";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

type Summary = { scan: Scan; findings: Finding[]; stages: ScanStage[] };

export default function ScanHistoryPage() {
  const [summaries, setSummaries] = useState<Summary[] | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<ScanStatus | "all">("all");
  const [targetTypeFilter, setTargetTypeFilter] = useState<TargetType | "all">("all");
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);

  const load = useCallback(() => {
    let cancelled = false;
    async function load() {
      try {
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
        if (!cancelled) {
          setSummaries(details);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load scan history.");
          setSummaries([]);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  async function deleteScan(scan: Scan) {
    if (!window.confirm(`Delete the scan history for ${scan.target}? This cannot be undone.`)) return;
    setDeletingId(scan.id);
    try {
      await api.deleteScan(scan.id);
      setSummaries((current) => current?.filter((summary) => summary.scan.id !== scan.id) ?? []);
      toast.success("Scan deleted");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not delete this scan.");
    } finally {
      setDeletingId(null);
    }
  }

  async function clearHistory() {
    if (!window.confirm("Delete your entire scan history? This cannot be undone.")) return;
    setClearing(true);
    try {
      await api.clearScanHistory();
      setSummaries([]);
      toast.success("Scan history cleared");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not clear scan history.");
    } finally {
      setClearing(false);
    }
  }

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
          <>
            <Button variant="destructive" disabled={clearing || !summaries?.length} onClick={() => void clearHistory()}>
              <Trash2 className="size-4" />
              {clearing ? "Clearing…" : "Clear history"}
            </Button>
            <Button render={<Link href="/scans/new" />}>
              <Plus className="size-4" />
              New scan
            </Button>
          </>
        }
      />

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load history</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <SectionCard
        title="Filters"
        description="Comparison is only meaningful between repeated scans of the same target, so this view keeps the raw rows visible."
      >
        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px_220px]">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(event) => setQuery(event.target.value)} className="pl-9" placeholder="Search by repository or server URL" aria-label="Search scan history" />
          </div>
          <select
            aria-label="Filter scans by status"
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
            aria-label="Filter scans by target type"
            className="h-9 rounded-lg border border-border bg-background px-3 text-sm"
            value={targetTypeFilter}
            onChange={(event) => setTargetTypeFilter(event.target.value as TargetType | "all")}
          >
            <option value="all">All target types</option>
            <option value="github_repo">GitHub repository</option>
            <option value="live_mcp_server">Live MCP server</option>
            <option value="config_paste">Pasted configuration</option>
            <option value="local_path">Local path (CLI)</option>
          </select>
        </div>
      </SectionCard>

      <SectionCard title="Scans" description={`${filtered.length} visible scan${filtered.length === 1 ? "" : "s"}.`}>
        <div className="space-y-3">
          {summaries === null
            ? Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-32 rounded-2xl" />)
            : filtered.length > 0
              ? filtered.map((summary) => (
                  <ScanHistoryRow
                    key={summary.scan.id}
                    summary={summary}
                    deleting={deletingId === summary.scan.id}
                    onDelete={() => void deleteScan(summary.scan)}
                  />
                ))
              : (
                  <EmptyState
                    title={summaries.length === 0 ? "No scans yet" : "No scans match these filters"}
                    body={summaries.length === 0 ? "Start a scan to build an auditable history of coverage and findings." : "Adjust the target, status, or target-type filters to see more results."}
                  />
                )}
        </div>
      </SectionCard>
    </div>
  );
}

function ScanHistoryRow({ summary, deleting, onDelete }: { summary: Summary; deleting: boolean; onDelete: () => void }) {
  const counts = summarizeFindings(summary.findings.filter((finding) => !finding.not_tested && finding.triage_status === "open"));

  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-2xl border border-border bg-background/80 p-4 transition-colors hover:bg-muted/30 lg:flex-row lg:items-center">
      <Link href={`/scans/${summary.scan.id}`} className="grid min-w-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto] lg:items-center">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={summary.scan.status} />
            <span className="text-sm text-muted-foreground">{TARGET_TYPE_LABELS[summary.scan.target_type]}</span>
            <span className="text-sm text-muted-foreground">{SCAN_SOURCE_LABELS[summary.scan.source]}</span>
          </div>
          <div className="break-all text-base font-medium">{summary.scan.target}</div>
        </div>

        <div className="grid gap-2 text-sm text-muted-foreground sm:grid-cols-2">
          <span>Finished: {formatDateTime(summary.scan.completed_at ?? summary.scan.created_at)}</span>
          <span>Duration: {formatDuration(summary.scan.created_at, summary.scan.completed_at)}</span>
          <span>Critical: {counts.critical}</span>
          <span>High: {counts.high}</span>
        </div>

        <div className="flex flex-col items-end gap-1">
          {counts.critical > 0 ? <SeverityBadge severity="critical" /> : null}
          {counts.high > 0 ? <SeverityBadge severity="high" /> : null}
          {counts.critical === 0 && counts.high === 0 ? (
            <span className="text-xs text-muted-foreground">No critical or high findings</span>
          ) : null}
        </div>
      </Link>
      <Button variant="ghost" size="icon" aria-label={`Delete scan for ${summary.scan.target}`} disabled={deleting} onClick={onDelete}>
        <Trash2 className="size-4 text-destructive" />
      </Button>
    </article>
  );
}
