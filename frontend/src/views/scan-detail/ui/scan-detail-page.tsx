"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { AlertTriangle, Ban, CheckCircle2, CircleDashed, Loader2, MinusCircle, Search, Sparkles, XCircle } from "lucide-react";
import { ApiError } from "@/shared/api";
import { billingApi } from "@/entities/billing";
import { findingApi } from "@/entities/finding";
import { scanApi } from "@/entities/scan";
import type { Finding, Severity } from "@/entities/finding";
import type { Scan, ScanDiff, ScanStage } from "@/entities/scan";
import { OWASP_CATEGORY_LABELS } from "@/entities/finding";
import { GRADE_LABELS, GRADE_STYLES, STAGE_LABELS, STAGE_ORDER } from "@/entities/scan";
import { summarizeFindings } from "@/entities/finding";
import { SCAN_SOURCE_LABELS, TARGET_TYPE_LABELS, summarizeCoverage, verdictLabel } from "@/entities/scan";
import { formatDateTime, formatDuration } from "@/shared/lib/format";
import { PageHeader, SectionCard, EmptyState } from "@/shared/ui";
import { Select } from "@/shared/ui/select";
import { StatusBadge } from "@/entities/scan";
import { SeverityBadge } from "@/entities/finding";
import { Button } from "@/shared/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Input } from "@/shared/ui/input";
import { Card, CardContent } from "@/shared/ui/card";
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
  const [cancelling, setCancelling] = useState(false);
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

  /** End a scan that is still open.
   *
   *  This stops the record, not the worker: the container is left to finish
   *  and be discarded. It exists because a scan that cannot finish also could
   *  not be deleted - the delete endpoint refuses anything still running - so
   *  a stuck row was permanent. A cancelled scan is `failed` and carries no
   *  grade, because nothing was established about the target.
   */
  const cancelScan = useCallback(async () => {
    setCancelling(true);
    try {
      await scanApi.cancelScan(scanId);
      toast.success("Scan cancelled. It produced no security assessment.");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not cancel this scan.");
    } finally {
      setCancelling(false);
    }
  }, [scanId, load]);

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
    () => findings,
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

  const coverage = summarizeCoverage(stages);
  const counts = summarizeFindings(openFindings);
  const resultSummary = verdictLabel(scan, counts);

  return (
    <div className="space-y-6">
      <PageHeader
        pretitle="Scan"
        title="Scan result"
        description="Review the target, actual coverage, score, urgent findings, and the limitations that still need separate verification."
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

      <Card className="bg-card/80">
        <CardContent className="grid gap-6 pt-6 lg:grid-cols-[minmax(0,1.3fr)_300px]">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={scan.status} />
              <span className="text-sm text-muted-foreground">{TARGET_TYPE_LABELS[scan.target_type]}</span>
              <span className="text-sm text-muted-foreground">{SCAN_SOURCE_LABELS[scan.source]}</span>
            </div>
            <div className="break-all text-2xl font-semibold tracking-tight">{scan.target}</div>

            <div className="flex flex-wrap items-center gap-4">
              <span
                className={`grid size-16 shrink-0 place-items-center rounded-xl border text-3xl font-semibold tabular-nums ${
                  scan.grade ? GRADE_STYLES[scan.grade] : "border-border bg-muted text-muted-foreground"
                }`}
                role="img"
                aria-label={
                  scan.grade
                    ? `Grade ${scan.grade}: ${GRADE_LABELS[scan.grade]}`
                    : "Not graded: this scan could not be graded"
                }
              >
                {scan.grade ?? "?"}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium">
                  {scan.grade ? GRADE_LABELS[scan.grade] : "Not graded"}
                </p>
                <p className="text-sm text-muted-foreground tabular-nums">
                  {scan.risk_score === null
                    ? "Risk score unavailable"
                    : `Risk score ${scan.risk_score}/100`}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">{resultSummary}</p>
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <MetaBlock label="Scanned at" value={formatDateTime(scan.completed_at ?? scan.created_at)} />
              <MetaBlock label="Duration" value={formatDuration(scan.created_at, scan.completed_at)} />
              <MetaBlock label="Coverage" value={`${coverage.completed}/${stages.length || 6} stages complete`} />
            </div>
          </div>

          <div className="rounded-xl border border-border bg-background/70 p-5">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Active findings</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
              <CountRow severity="critical" count={counts.critical} />
              <CountRow severity="high" count={counts.high} />
              <CountRow severity="medium" count={counts.medium} />
              <CountRow severity="low" count={counts.low} />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* SCAN -> EVIDENCE -> RISK -> EXPLANATION -> RECOMMENDATION -> POLICY.
          This is the explanation and recommendation, ahead of the finding
          list rather than under it: a reader who stops here should already
          know what to do, and one who continues should know what they are
          looking for. */}
      {scan.risk_summary ? (
        <SectionCard
          title="Risk summary"
          description="What this scan found, what it could mean, and what to do about it."
        >
          <div className="space-y-4">
            <p className="text-lg font-medium">{scan.risk_summary.headline}</p>
            <p className="max-w-3xl text-sm leading-6">{scan.risk_summary.explanation}</p>
            <dl className="grid gap-4 sm:grid-cols-2">
              <div>
                <dt className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                  Potential impact
                </dt>
                <dd className="mt-1.5 text-sm leading-6">{scan.risk_summary.potential_impact}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                  Recommended action
                </dt>
                <dd className="mt-1.5 text-sm leading-6">{scan.risk_summary.recommended_action}</dd>
              </div>
            </dl>
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-background/70 px-4 py-3">
              <span className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                Suggested policy
              </span>
              <span className="font-mono text-sm font-medium">
                {scan.risk_summary.suggested_policy.replace(/_/g, " ")}
              </span>
              <span className="text-xs text-muted-foreground">
                A recommendation, not an automatic action.
              </span>
            </div>
          </div>
        </SectionCard>
      ) : null}

      {scan.status === "incomplete" ? (
        <Alert variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>Partial scan coverage</AlertTitle>
          <AlertDescription>
            Required scanners did not complete for {scan.unreliable_stages.map((stage) => STAGE_LABELS[stage]).join(", ")}. No grade is given for this scan: the findings below are real, but they do not add up to a complete assessment.
          </AlertDescription>
        </Alert>
      ) : null}

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
            Aevrin recomputed the risk score and grade from the uploaded findings and preserved the CLI stages, timestamps, and evidence. The local findings are client-reported and were not independently re-scanned by the API.
          </AlertDescription>
        </Alert>
      ) : null}

      {scan.status === "queued" || scan.status === "running" ? (
        <SectionCard
          title="Scan progress"
          description="Stage-level status updates remain visible so you can leave the page and come back without losing context."
          action={
            <Button
              size="sm"
              variant="outline"
              disabled={cancelling}
              onClick={() => void cancelScan()}
            >
              {cancelling ? <Loader2 className="size-4 animate-spin" /> : <Ban className="size-4" />}
              Cancel scan
            </Button>
          }
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
              <div className="space-y-3">
                {filteredFindings.map((finding) => {
                  const params = new URLSearchParams(searchParams.toString());
                  const returnTo = params.toString() ? `${pathname}?${params.toString()}` : pathname;
                  return (
                    <div
                      key={finding.id}
                      className="flex items-start gap-2 rounded-xl border border-border bg-background/80 transition-colors hover:bg-muted/30"
                    >
                    <button
                      type="button"
                      onClick={() =>
                        router.push(
                          `/scans/${scan.id}/findings/${finding.id}?returnTo=${encodeURIComponent(returnTo)}`,
                        )
                      }
                      className="min-w-0 flex-1 rounded-xl p-4 text-left"
                    >
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                        <div className="space-y-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <SeverityBadge severity={finding.severity} />
                            {finding.rule_id ? (
                              <span className="rounded-full border border-border bg-muted px-2 py-0.5 font-mono text-xs font-medium">
                                {finding.rule_id}
                              </span>
                            ) : null}
                            {/* One card per rule verdict, with the count, not
                                one card per affected tool. Five tools missing
                                a timeout is one thing to fix. */}
                            {finding.occurrence_count > 1 ? (
                              <span className="text-xs text-muted-foreground tabular-nums">
                                ×{finding.occurrence_count}
                              </span>
                            ) : null}
                            {finding.rule_id ? (
                              <span className="rounded-full border border-border px-2 py-0.5 font-mono text-xs text-muted-foreground">
                                {finding.rule_id}
                              </span>
                            ) : null}
                            {finding.occurrence_count > 1 ? (
                              <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
                                &times;{finding.occurrence_count} tools
                              </span>
                            ) : null}
                            <span className="text-sm text-muted-foreground">
                              {OWASP_CATEGORY_LABELS[finding.owasp_category] ?? finding.owasp_category}
                            </span>
                          </div>
                          <p className="text-base font-medium">{finding.title}</p>
                          {finding.file_path ? (
                            <p className="font-mono text-[12px] text-brand-text">
                              {finding.file_path}
                              {finding.line_start ? `:${finding.line_start}` : ""}
                            </p>
                          ) : null}
                          <p className="text-sm leading-6 text-muted-foreground line-clamp-2">
                            {finding.description}
                          </p>
                          {finding.affected_tools.length > 0 ? (
                            <p className="text-xs text-muted-foreground">
                              <span className="uppercase tracking-[0.12em]">Affected tools</span>{" "}
                              <span className="font-mono">
                                {finding.affected_tools.slice(0, 6).join(", ")}
                                {finding.affected_tools.length > 6
                                  ? ` +${finding.affected_tools.length - 6} more`
                                  : ""}
                              </span>
                            </p>
                          ) : null}
                          {finding.evidence.length > 0 ? (
                            <p className="text-xs text-muted-foreground">
                              <span className="uppercase tracking-[0.12em]">Evidence</span>{" "}
                              <span className="font-mono">{finding.evidence[0]}</span>
                              {finding.evidence.length > 1
                                ? ` +${finding.evidence.length - 1} more`
                                : ""}
                            </p>
                          ) : null}
                          {/* Only surfaced in the list when the AI disagreed
                              with the scanner. "AI agrees" on every row would
                              be noise on the one screen that has to stay
                              scannable; the full review is on the detail
                              page either way. */}
                          {finding.llm_classification === "likely_false_positive" ? (
                            <p className="flex items-center gap-1.5 text-xs text-chart-1">
                              <Sparkles className="size-3" />
                              AI review: likely a false positive
                            </p>
                          ) : finding.llm_severity && finding.llm_severity !== finding.severity ? (
                            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                              <Sparkles className="size-3" />
                              AI review suggests {finding.llm_severity}
                            </p>
                          ) : null}
                        </div>
                        <div className="space-y-1 text-right text-sm text-muted-foreground">
                          <div>{finding.tool}</div>
                          <div>{finding.file_path ? `${finding.file_path}${finding.line_start ? `:${finding.line_start}` : ""}` : finding.manifest_field ?? "Location unavailable"}</div>
                        </div>
                      </div>
                    </button>
                    </div>
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

        </div>
      </div>
    </div>
  );
}

function MetaBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-background/70 p-4">
      <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <p className="mt-2 text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

function CountRow({ severity, count }: { severity: Severity; count: number }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-border bg-background/80 px-3 py-2.5">
      <SeverityBadge severity={severity} />
      <span className="text-lg font-semibold">{count}</span>
    </div>
  );
}
