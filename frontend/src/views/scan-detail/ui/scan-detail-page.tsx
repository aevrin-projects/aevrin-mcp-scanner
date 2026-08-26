"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, CircleDashed, Loader2, MinusCircle, Search, Sparkles, XCircle } from "lucide-react";
import { ApiError } from "@/shared/api";
import { billingApi } from "@/entities/billing";
import { findingApi } from "@/entities/finding";
import { scanApi } from "@/entities/scan";
import type { Finding } from "@/entities/finding";
import type { Scan, ScanDiff, ScanStage } from "@/entities/scan";
import { STAGE_LABELS, STAGE_ORDER } from "@/entities/scan";
import { summarizeFindings } from "@/entities/finding";
import { SCAN_SOURCE_LABELS } from "@/entities/scan";
import { PageHeader, SectionCard, EmptyState } from "@/shared/ui";
import { FindingRow } from "./finding-row";
import { ReportMasthead } from "./report-masthead";
import { Select } from "@/shared/ui/select";
import { Button } from "@/shared/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Input } from "@/shared/ui/input";
import { Skeleton } from "@/shared/ui/skeleton";

const POLL_INTERVAL_MS = 2000;

const STAGE_ICON: Record<ScanStage["status"], React.ReactNode> = {
  pending: <CircleDashed className="size-4 text-muted-foreground" />,
  running: <Loader2 className="size-4 animate-spin text-brand-text" />,
  done: <CheckCircle2 className="size-4 text-brand-text" />,
  failed: <XCircle className="size-4 text-severity-critical" />,
  skipped: <MinusCircle className="size-4 text-muted-foreground" />,
};

export function ScanDetailClient({ scanId }: { scanId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [scan, setScan] = useState<Scan | null>(null);
  const [stages, setStages] = useState<ScanStage[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [diff, setDiff] = useState<ScanDiff | null>(null);
  const [canExport, setCanExport] = useState<boolean | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const [scanData, stagesData] = await Promise.all([scanApi.getScan(scanId), scanApi.getScanStages(scanId)]);
      setScan(scanData);
      setStages(stagesData);
      setLoadError(null);

      if (scanData.status === "completed" || scanData.status === "incomplete" || scanData.status === "failed") {
        const findingsData = await findingApi.getScanFindings(scanId);
        setFindings(findingsData);
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not load this scan.";
      setLoadError(message);
    }
  }, [scanId]);

  useEffect(() => {
    // Initial fetch plus polling keeps the page synchronized with the scan worker.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    intervalRef.current = setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [load]);

  useEffect(() => {
    billingApi.getSubscription().then((subscription) => {
      setCanExport(subscription.effective_tier !== "free");
    }).catch(() => setCanExport(null));
  }, []);

  const query = searchParams.get("q") ?? "";
  const severityFilter = searchParams.get("severity") ?? "all";
  const triageFilter = searchParams.get("triage") ?? "all";

  function updateFilter(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (!value || value === "all") {
      params.delete(key);
    } else {
      params.set(key, value);
    }
    router.replace(params.toString() ? `${pathname}?${params.toString()}` : pathname);
  }

  const activeFindings = useMemo(
    () => findings.filter((finding) => !finding.not_tested && !finding.excluded_path),
    [findings],
  );

  const excludedPathFindings = useMemo(
    () => findings.filter((finding) => finding.excluded_path),
    [findings],
  );

  const openFindings = useMemo(
    () => activeFindings.filter((finding) => finding.triage_status === "open"),
    [activeFindings],
  );

  const filteredFindings = useMemo(() => {
    return activeFindings.filter((finding) => {
      if (severityFilter !== "all" && finding.severity !== severityFilter) return false;
      if (triageFilter !== "all" && finding.triage_status !== triageFilter) return false;
      if (
        query &&
        !`${finding.title} ${finding.description} ${finding.tool} ${finding.file_path ?? ""}`
          .toLowerCase()
          .includes(query.toLowerCase())
      ) {
        return false;
      }
      return true;
    });
  }, [activeFindings, query, severityFilter, triageFilter]);

  // "Did my fix actually work?" is the question a rescan has to answer, and
  // it cannot be answered from a findings list alone when two findings share
  // a title in different files.
  useEffect(() => {
    if (!scan || (scan.status !== "completed" && scan.status !== "incomplete")) return;
    const id = window.setTimeout(() => {
      void scanApi.getScanDiff(scanId).then(setDiff).catch(() => setDiff(null));
    }, 0);
    return () => window.clearTimeout(id);
  }, [scan, scanId]);

  if (loadError && !scan) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="size-4" />
        <AlertTitle>Could not load scan</AlertTitle>
        <AlertDescription>{loadError}</AlertDescription>
      </Alert>
    );
  }

  if (!scan) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-24 rounded-xl" />
        <Skeleton className="h-80 rounded-xl" />
      </div>
    );
  }

  const counts = summarizeFindings(openFindings);
  const limitations = findings.filter((finding) => finding.not_tested);

  return (
    <div className="space-y-6">
      {/* The masthead below is the report's title. This row is only the
          actions, so the page opens on the verdict rather than on the words
          "Scan result", which never told anyone anything. */}
      <PageHeader
        pretitle="Scan"
        title={SCAN_SOURCE_LABELS[scan.source]}
        actions={
          <>
            {scan.target_type === "local_path" ? (
              <Button nativeButton={false} render={<Link href="/integrations" />} variant="outline">Rescan with CLI</Button>
            ) : (
              <Button nativeButton={false} render={<Link href={`/scans/new?mode=${scan.target_type}&target=${encodeURIComponent(scan.target)}`} />} variant="outline">Rescan target</Button>
            )}
            {(scan.status === "completed" || scan.status === "incomplete") && canExport ? (
              <Button
                variant="outline"
                disabled={exporting}
                onClick={async () => {
                  setExporting(true);
                  try {
                    const { url } = await scanApi.exportReport(scanId);
                    window.open(url, "_blank", "noopener,noreferrer");
                  } catch (err) {
                    toast.error(err instanceof ApiError ? err.message : "Could not export the report.");
                  } finally {
                    setExporting(false);
                  }
                }}
              >
                {exporting ? "Exporting…" : "Export report"}
              </Button>
            ) : null}
            {(scan.status === "completed" || scan.status === "incomplete") && canExport === false ? (
              <Button nativeButton={false} render={<Link href="/pricing" />} variant="outline">Upgrade to export</Button>
            ) : null}
          </>
        }
      />

      <ReportMasthead scan={scan} stages={stages} counts={counts} openCount={openFindings.length} />

      {/* Distinct from the incomplete banner above: the scanners all ran and
          every finding is listed, only the AI second opinion was capped.
          Informational, not destructive: nothing here is unreliable. */}
      {scan.triage_note ? (
        <Alert>
          <Sparkles className="size-4" />
          <AlertTitle>AI review was capped for this scan</AlertTitle>
          <AlertDescription>{scan.triage_note}</AlertDescription>
        </Alert>
      ) : null}

      {scan.status === "failed" ? (
        <Alert variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>Scan failed</AlertTitle>
          <AlertDescription>
            This scan did not complete. Any results below are not a reliable assessment of this target, rescan before making a decision.
          </AlertDescription>
        </Alert>
      ) : null}

      {scan.source === "cli" ? (
        <Alert>
          <AlertTriangle className="size-4" />
          <AlertTitle>Uploaded from the authenticated CLI</AlertTitle>
          <AlertDescription>
            Aevrin recomputed the score from the uploaded findings and preserved the CLI stages, timestamps, and evidence. The local findings are client-reported and were not independently re-scanned by the API.
          </AlertDescription>
        </Alert>
      ) : null}

      {scan.status === "queued" || scan.status === "running" ? (
        <SectionCard
          title="Scan progress"
          description="Stage-level status updates remain visible so you can leave the page and come back without losing context."
        >
          <div className="space-y-3">
            {STAGE_ORDER.map((name) => {
              const stage = stages.find((entry) => entry.name === name) ?? {
                name,
                status: "pending" as const,
                error: null,
                started_at: null,
                finished_at: null,
              };

              return (
                <div key={stage.name} className="flex items-center justify-between rounded-xl border border-border bg-background/70 px-4 py-3 text-sm">
                  <div className="flex items-center gap-3">
                    {STAGE_ICON[stage.status]}
                    <span>{STAGE_LABELS[stage.name]}</span>
                  </div>
                  <span className="text-muted-foreground">{stage.status}</span>
                </div>
              );
            })}
          </div>
        </SectionCard>
      ) : null}

      {/* The answer to "did my fix work". Without this, a rescan that
          resolved one of three same-titled findings looked identical to one
          that resolved nothing. */}
      {diff && diff.previous_scan_id && (diff.resolved.length > 0 || diff.introduced.length > 0) ? (
        <section className="rounded-xl border border-border bg-card p-4">
          <h2 className="text-sm font-medium">Since your last scan of this target</h2>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            {diff.resolved.length > 0 ? (
              <div>
                <p className="flex items-center gap-1.5 text-[13px] text-chart-1">
                  <CheckCircle2 className="size-3.5" />
                  {diff.resolved.length} resolved
                </p>
                <ul className="mt-1.5 space-y-1">
                  {diff.resolved.slice(0, 5).map((d, i) => (
                    <li key={i} className="text-[12px] text-muted-foreground">
                      <span className="line-through">{d.title}</span>
                      {d.file_path ? <span className="ml-1.5 font-mono">{d.file_path}</span> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {diff.introduced.length > 0 ? (
              <div>
                <p className="flex items-center gap-1.5 text-[13px] text-severity-high">
                  <AlertTriangle className="size-3.5" />
                  {diff.introduced.length} new
                </p>
                <ul className="mt-1.5 space-y-1">
                  {diff.introduced.slice(0, 5).map((d, i) => (
                    <li key={i} className="text-[12px] text-muted-foreground">
                      {d.title}
                      {d.file_path ? <span className="ml-1.5 font-mono">{d.file_path}</span> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
          <p className="mt-3 text-[11px] text-muted-foreground">
            {diff.unchanged_count} finding{diff.unchanged_count === 1 ? "" : "s"} unchanged. A finding is matched
            on title, file, and scanner, so the same issue in a different file counts separately.
          </p>
        </section>
      ) : null}

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.35fr)_360px]">
        <SectionCard
          title="Findings"
          description="Search and filter the active findings for this scan. Limitation notices remain separate from actual findings."
        >
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_180px_180px]">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(event) => updateFilter("q", event.target.value)}
                  className="pl-9"
                  placeholder="Search title, tool, path, or description"
                  aria-label="Search findings"
                />
              </div>
              <Select
                aria-label="Filter findings by severity"
                value={severityFilter}
                onChange={(event) => updateFilter("severity", event.target.value)}
              >
                <option value="all">All severities</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
                <option value="info">Info</option>
              </Select>
              <Select
                aria-label="Filter findings by triage status"
                value={triageFilter}
                onChange={(event) => updateFilter("triage", event.target.value)}
              >
                <option value="all">All statuses</option>
                <option value="open">Open</option>
                <option value="fixed">Fixed</option>
                <option value="false_positive">False positive</option>
              </Select>
            </div>

            {filteredFindings.length === 0 ? (
              <EmptyState
                title={activeFindings.length === 0 ? "No active findings in completed checks" : "No findings match these filters"}
                body={
                  activeFindings.length === 0
                    ? "That does not mean the target is fully safe. Review the stage coverage and documented limitations below before trusting the result."
                    : "Change the search query or filters to return to the current result set."
                }
                icon="attention"
              />
            ) : (
              <div className="-mx-3">
                {filteredFindings.map((finding) => {
                  const params = new URLSearchParams(searchParams.toString());
                  const returnTo = params.toString() ? `${pathname}?${params.toString()}` : pathname;
                  return (
                    <FindingRow
                      key={finding.id}
                      finding={finding}
                      href={`/scans/${scan.id}/findings/${finding.id}?returnTo=${encodeURIComponent(returnTo)}`}
                    />
                  );
                })}
              </div>
            )}
          </div>
        </SectionCard>

        <div className="space-y-6">
          <SectionCard
            title="Coverage and limitations"
            description="Keep skipped and failed scanner stages visible so the score is not mistaken for complete coverage."
          >
            <div className="space-y-3">
              {STAGE_ORDER.map((name) => {
                const stage = stages.find((entry) => entry.name === name);
                if (!stage) return null;
                return (
                  <div key={stage.name} className="rounded-xl border border-border bg-background/80 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        {STAGE_ICON[stage.status]}
                        <span className="font-medium text-foreground">{STAGE_LABELS[stage.name]}</span>
                      </div>
                      <span className="text-sm text-muted-foreground">{stage.status}</span>
                    </div>
                    {stage.error ? (
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">{stage.error}</p>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </SectionCard>

          <SectionCard title="Score method" description="The current documented method starts at 100 and subtracts severity-weighted findings.">
            <div className="space-y-3 text-sm leading-6 text-muted-foreground">
              <p>Critical findings subtract 40 points each, high subtract 20, medium subtract 8, and low subtract 3.</p>
              <p>Later triage changes active-risk counts and hook decisions, but preserves the original scan-time score for auditability and CLI/dashboard consistency.</p>
              <p>The score never guarantees safety. Coverage and failed stages must be read beside it.</p>
            </div>
          </SectionCard>

          {excludedPathFindings.length > 0 ? (
            <Alert>
              <AlertTriangle className="size-4" />
              <AlertTitle>{excludedPathFindings.length} finding(s) excluded from the score</AlertTitle>
              <AlertDescription>
                These matched a test or fixture path convention (a <code>fixtures/</code>-style directory, or a
                filename like <code>*.test.ts</code>) and are hidden from the results above and excluded from
                scoring, sample code deliberately written to look vulnerable is not a real issue in the shipped
                server.
              </AlertDescription>
            </Alert>
          ) : null}

          {limitations.map((finding) => (
            <Alert key={finding.id}>
              <AlertTriangle className="size-4" />
              <AlertTitle>{finding.title}</AlertTitle>
              <AlertDescription>{finding.description}</AlertDescription>
            </Alert>
          ))}
        </div>
      </div>
    </div>
  );
}


