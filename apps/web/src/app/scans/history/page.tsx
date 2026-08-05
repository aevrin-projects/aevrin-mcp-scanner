"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronRight, Folder, FolderOpen, Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { Finding, Scan, ScanStage, ScanStatus, TargetType } from "@/lib/types";
import { EmptyState, PageHeader, SectionCard } from "@/components/product-ui";
import { StatusBadge } from "@/components/status-badge";
import { Input } from "@/components/ui/input";
import {
  SCAN_SOURCE_LABELS,
  TARGET_TYPE_LABELS,
  formatDateTime,
  formatDuration,
  summarizeCoverage,
  summarizeFindings,
} from "@/lib/presentation";
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

  /* Scans are grouped into one folder per target. Repeat scans of the same
     repository are the common case, and a flat list of them turned this page
     into hundreds of near-identical rows you had to scroll past to reach a
     different target. The folder header carries everything you'd scan the
     list for — count, worst severity, latest score, latest run — so opening
     one is a choice, not a requirement. */
  const folders = useMemo(() => {
    const byTarget = new Map<string, Summary[]>();
    for (const summary of filtered) {
      const list = byTarget.get(summary.scan.target);
      if (list) list.push(summary);
      else byTarget.set(summary.scan.target, [summary]);
    }

    return [...byTarget.entries()]
      .map(([target, scans]) => {
        const ordered = [...scans].sort(
          (a, b) => new Date(b.scan.created_at).getTime() - new Date(a.scan.created_at).getTime(),
        );
        const latest = ordered[0];
        const totals = ordered.reduce(
          (acc, item) => {
            const counts = summarizeFindings(
              item.findings.filter((finding) => !finding.not_tested && finding.triage_status === "open"),
            );
            acc.critical += counts.critical;
            acc.high += counts.high;
            return acc;
          },
          { critical: 0, high: 0 },
        );
        return { target, scans: ordered, latest, totals };
      })
      .sort(
        (a, b) =>
          new Date(b.latest.scan.created_at).getTime() - new Date(a.latest.scan.created_at).getTime(),
      );
  }, [filtered]);

  // Most recent target is open on arrival; the rest start closed. A search
  // narrow enough to hit one folder opens it, so filtering never lands you on
  // a screen of collapsed rows.
  const autoOpen = folders.length === 1 ? folders[0].target : (folders[0]?.target ?? null);
  const [openTargets, setOpenTargets] = useState<Set<string>>(new Set());
  const isOpen = (target: string) => openTargets.has(target) || (openTargets.size === 0 && target === autoOpen);

  function toggleFolder(target: string) {
    setOpenTargets((current) => {
      const next = new Set(current.size === 0 && autoOpen ? [autoOpen] : current);
      if (next.has(target)) next.delete(target);
      else next.add(target);
      return next;
    });
  }

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
            <Button nativeButton={false} render={<Link href="/scans/new" />}>
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

      {/* Filters live in the same card as the results — a separate "Filters"
          panel above them added a whole card of height for three inputs. */}
      <SectionCard
        title="Scans"
        description={`${filtered.length} scan${filtered.length === 1 ? "" : "s"} across ${folders.length} target${folders.length === 1 ? "" : "s"}.`}
      >
        <div className="grid items-start gap-3 md:grid-cols-[minmax(0,1fr)_200px_200px]">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="pl-9"
              placeholder="Search by repository or server URL"
              aria-label="Search scan history"
            />
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

        <div className="panel-rise mt-5 space-y-2.5">
          {summaries === null ? (
            Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-14 rounded-xl" />)
          ) : folders.length > 0 ? (
            folders.map((folder, index) => (
              <TargetFolder
                key={folder.target}
                index={index}
                folder={folder}
                open={isOpen(folder.target)}
                onToggle={() => toggleFolder(folder.target)}
                deletingId={deletingId}
                onDelete={(scan) => void deleteScan(scan)}
              />
            ))
          ) : (
            <EmptyState
              title={summaries.length === 0 ? "No scans yet" : "No scans match these filters"}
              body={
                summaries.length === 0
                  ? "Start a scan to build an auditable history of coverage and findings."
                  : "Adjust the target, status, or target-type filters to see more results."
              }
            />
          )}
        </div>
      </SectionCard>
    </div>
  );
}

type Folder = {
  target: string;
  scans: Summary[];
  latest: Summary;
  totals: { critical: number; high: number };
};

/** One target, collapsed to a single summary row until you open it. */
function TargetFolder({
  folder,
  open,
  onToggle,
  deletingId,
  onDelete,
  index,
}: {
  folder: Folder;
  open: boolean;
  onToggle: () => void;
  deletingId: string | null;
  onDelete: (scan: Scan) => void;
  index: number;
}) {
  const { target, scans, latest, totals } = folder;

  return (
    <section
      className="overflow-hidden rounded-xl border border-border bg-background/80"
      style={{ "--i": index } as React.CSSProperties}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40"
      >
        <ChevronRight
          aria-hidden="true"
          className={`size-4 shrink-0 text-muted-foreground transition-transform duration-200 ${open ? "rotate-90" : ""}`}
        />
        {open ? (
          <FolderOpen aria-hidden="true" className="size-4 shrink-0 text-brand-text" />
        ) : (
          <Folder aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
        )}

        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-foreground">
            {target.replace(/^https?:\/\//, "")}
          </span>
          <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
            {scans.length} scan{scans.length === 1 ? "" : "s"} · {TARGET_TYPE_LABELS[latest.scan.target_type]} ·
            last run {formatDateTime(latest.scan.completed_at ?? latest.scan.created_at)}
          </span>
        </span>

        <span className="flex shrink-0 items-center gap-3">
          {totals.critical > 0 ? (
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <span aria-hidden="true" className="size-1.5 rounded-full bg-severity-critical" />
              {totals.critical}
              <span className="sr-only"> critical findings</span>
            </span>
          ) : null}
          {totals.high > 0 ? (
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <span aria-hidden="true" className="size-1.5 rounded-full bg-severity-high" />
              {totals.high}
              <span className="sr-only"> high findings</span>
            </span>
          ) : null}
          <StatusBadge status={latest.scan.status} />
          <span className="w-8 text-right text-sm font-medium tabular-nums">{latest.scan.score ?? "—"}</span>
        </span>
      </button>

      {/* grid-rows 0fr → 1fr animates to an unknown height without measuring. */}
      <div
        className={`grid transition-[grid-template-rows] duration-300 ease-out ${open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}
      >
        <div className="overflow-hidden">
          <ul className="border-t border-border">
            {scans.map((summary) => (
              <li key={summary.scan.id}>
                <ScanHistoryRow
                  summary={summary}
                  deleting={deletingId === summary.scan.id}
                  onDelete={() => onDelete(summary.scan)}
                  tabbable={open}
                />
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

/** One run inside a folder. Deliberately a single line: the folder header
 *  already carried the target, so a row only needs when it ran, how much it
 *  covered, and what it found. */
function ScanHistoryRow({
  summary,
  deleting,
  onDelete,
  tabbable,
}: {
  summary: Summary;
  deleting: boolean;
  onDelete: () => void;
  tabbable: boolean;
}) {
  const counts = summarizeFindings(
    summary.findings.filter((finding) => !finding.not_tested && finding.triage_status === "open"),
  );
  const coverage = summarizeCoverage(summary.stages);

  return (
    <div className="flex items-center gap-3 border-b border-border/60 px-4 py-2.5 transition-colors last:border-0 hover:bg-muted/30">
      <Link
        href={`/scans/${summary.scan.id}`}
        tabIndex={tabbable ? 0 : -1}
        className="flex min-w-0 flex-1 items-center gap-3"
      >
        <StatusBadge status={summary.scan.status} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] text-foreground">
            {formatDateTime(summary.scan.completed_at ?? summary.scan.created_at)}
          </span>
          <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
            {coverage.completed}/{summary.stages.length || 6} stages ·{" "}
            {formatDuration(summary.scan.created_at, summary.scan.completed_at)} ·{" "}
            {SCAN_SOURCE_LABELS[summary.scan.source]}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-3">
          {counts.critical > 0 ? (
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <span aria-hidden="true" className="size-1.5 rounded-full bg-severity-critical" />
              {counts.critical}
              <span className="sr-only"> critical findings</span>
            </span>
          ) : null}
          {counts.high > 0 ? (
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <span aria-hidden="true" className="size-1.5 rounded-full bg-severity-high" />
              {counts.high}
              <span className="sr-only"> high findings</span>
            </span>
          ) : null}
          <span className="w-8 text-right text-[13px] font-medium tabular-nums">{summary.scan.score ?? "—"}</span>
        </span>
      </Link>
      <Button
        variant="ghost"
        size="icon"
        tabIndex={tabbable ? 0 : -1}
        aria-label={`Delete the ${formatDateTime(summary.scan.completed_at ?? summary.scan.created_at)} scan for ${summary.scan.target}`}
        disabled={deleting}
        onClick={onDelete}
      >
        <Trash2 className="size-4 text-destructive" />
      </Button>
    </div>
  );
}
