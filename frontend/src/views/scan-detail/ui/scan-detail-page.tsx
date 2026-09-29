"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { AlertTriangle, Ban, CheckCircle2, CircleDashed, Loader2, MinusCircle, Search, Sparkles, XCircle } from "lucide-react";
import { ApiError } from "@/shared/api";
import { billingApi } from "@/entities/billing";
import { WORKSPACE_PERMISSIONS, useWorkspacePermission, workspaceAuthor } from "@/entities/organization";
import { findingApi } from "@/entities/finding";
import { scanApi } from "@/entities/scan";
import type { Finding, Severity } from "@/entities/finding";
import type { Scan, ScanDiff, ScanStage } from "@/entities/scan";
import { OWASP_CATEGORY_LABELS, TRIAGE_LABELS } from "@/entities/finding";
import { GRADE_LABELS, GRADE_STYLES, STAGE_LABELS, STAGE_ORDER } from "@/entities/scan";
import { summarizeFindings } from "@/entities/finding";
import { SCAN_SOURCE_LABELS, TARGET_TYPE_LABELS, summarizeCoverage, verdictLabel } from "@/entities/scan";
import { formatDateTime, formatDuration } from "@/shared/lib/format";
import { PageHeader, SectionCard, EmptyState } from "@/shared/ui";
import { Select } from "@/shared/ui/select";
import { StatusBadge } from "@/entities/scan";
import { ExplainButton } from "@/features/ai-explain";
import { SeverityBadge } from "@/entities/finding";
import { Button } from "@/shared/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Input } from "@/shared/ui/input";
import { Card, CardContent } from "@/shared/ui/card";
import { Skeleton } from "@/shared/ui/skeleton";

const POLL_INTERVAL_MS = 2000;

const STAGE_STATUS_LABELS: Record<ScanStage["status"], string> = {
  pending: "Waiting",
  running: "Running",
  done: "Done",
  failed: "Did not finish",
  skipped: "Skipped",
};

/** The scanner's suggested policy, in words. The value itself stays beside it. */
const POLICY_LABELS: Record<string, string> = {
  ALLOW: "Allow it.",
  REQUIRE_APPROVAL: "Allow it only if a person approves each use.",
  BLOCK: "Do not allow it.",
};

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
  const runScans = useWorkspacePermission(WORKSPACE_PERMISSIONS.scansRun);
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
      const message = err instanceof ApiError ? err.message : "We could not load this scan.";
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
      toast.success("Scan stopped. It did not check anything, so there is no result.");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "We could not stop this scan.");
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
        <AlertTitle>We could not load this scan</AlertTitle>
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
  const author = workspaceAuthor(scan);

  return (
    <div className="space-y-6">
      <PageHeader
        pretitle="Scan"
        title="Scan result"
        description="What we checked, what we found, how risky it is and what to do about it."
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
                    toast.error(err instanceof ApiError ? err.message : "We could not export the report.");
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
              {author ? <span className="text-sm text-muted-foreground">Run by {author}</span> : null}
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
                    ? "No risk score"
                    : `Risk score ${scan.risk_score} out of 100. Lower is safer.`}
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">{resultSummary}</p>
              </div>
            </div>

            {/* On-demand, and only once there is a result to explain. The
                explanation is built from this scan's own evidence, and the
                API refuses it to anyone who cannot read the scan. */}
            {scan.status === "completed" || scan.status === "incomplete" ? (
              <ExplainButton
                subjectType="scan"
                subjectId={scanId}
                label={scan.grade ? `Why is this grade ${scan.grade}?` : "Explain this result"}
              />
            ) : null}

            <div className="grid gap-4 sm:grid-cols-3">
              <MetaBlock label="Checked on" value={formatDateTime(scan.completed_at ?? scan.created_at)} />
              <MetaBlock label="Took" value={formatDuration(scan.created_at, scan.completed_at)} />
              <MetaBlock label="Checks finished" value={`${coverage.completed} of ${stages.length || STAGE_ORDER.length}`} />
            </div>
          </div>

          <div className="rounded-xl border border-border bg-background/70 p-5">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Problems not fixed yet</p>
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
          title="What this means"
          description="What we found, what could happen and what to do."
        >
          <div className="space-y-4">
            <p className="text-lg font-medium">{scan.risk_summary.headline}</p>
            <p className="max-w-3xl text-sm leading-6">{scan.risk_summary.explanation}</p>
            <dl className="grid gap-4 sm:grid-cols-2">
              <div>
                <dt className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                  What could happen?
                </dt>
                <dd className="mt-1.5 text-sm leading-6">{scan.risk_summary.potential_impact}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                  What should I do?
                </dt>
                <dd className="mt-1.5 text-sm leading-6">{scan.risk_summary.recommended_action}</dd>
              </div>
            </dl>
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-background/70 px-4 py-3">
              <span className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                What we suggest
              </span>
              <span className="text-sm font-medium">
                {POLICY_LABELS[scan.risk_summary.suggested_policy] ?? scan.risk_summary.suggested_policy}
              </span>
              <span className="font-mono text-xs text-muted-foreground">
                {scan.risk_summary.suggested_policy}
              </span>
              <span className="text-xs text-muted-foreground">
                This is advice. Aevrin does not change anything for you.
              </span>
            </div>
          </div>
        </SectionCard>
      ) : null}

      {scan.status === "incomplete" ? (
        <Alert variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>This scan could not finish every check</AlertTitle>
          <AlertDescription>
            These checks did not finish: {scan.unreliable_stages.map((stage) => STAGE_LABELS[stage]).join(", ")}. So there is no grade. The problems below are real, but the list may not be complete, and what was not checked is not safe just because nothing was found.
          </AlertDescription>
        </Alert>
      ) : null}

      {/* Distinct from the incomplete banner above: the scanners all ran and
          every finding is listed, only the AI second opinion was capped.
          Informational, not destructive: nothing here is unreliable. */}
      {scan.triage_note ? (
        <Alert>
          <Sparkles className="size-4" />
          <AlertTitle>The AI second opinion did not look at every problem</AlertTitle>
          <AlertDescription>{scan.triage_note}</AlertDescription>
        </Alert>
      ) : null}

      {scan.status === "failed" ? (
        <Alert variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>This scan did not finish</AlertTitle>
          <AlertDescription>
            The results below are not a full check of this target. Run the scan again before you decide anything.
          </AlertDescription>
        </Alert>
      ) : null}

      {scan.source === "cli" ? (
        <Alert>
          <AlertTriangle className="size-4" />
          <AlertTitle>This scan ran on your own computer</AlertTitle>
          <AlertDescription>
            It was run with the Aevrin CLI and uploaded. Aevrin worked out the score and grade again from the uploaded problems, and kept the checks, times and evidence as they were. Aevrin did not scan the target again itself.
          </AlertDescription>
        </Alert>
      ) : null}

      {scan.status === "queued" || scan.status === "running" ? (
        <SectionCard
          title="Scan progress"
          description="You can leave this page and come back. The progress is saved."
          action={
            // Only the person who started a scan can cancel it, even when a
            // colleague can read it through the workspace.
            scan.mine && runScans.allowed ? (
              <Button
                size="sm"
                variant="outline"
                disabled={cancelling}
                onClick={() => void cancelScan()}
              >
                {cancelling ? <Loader2 className="size-4 animate-spin" /> : <Ban className="size-4" />}
                Cancel scan
              </Button>
            ) : undefined
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
                  <span className="text-muted-foreground">{STAGE_STATUS_LABELS[stage.status]}</span>
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
          <h2 className="text-sm font-medium">
            {scan.mine ? "Since your last scan of this target" : "Since their last scan of this target"}
          </h2>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            {diff.resolved.length > 0 ? (
              <div>
                <p className="flex items-center gap-1.5 text-[13px] text-chart-1">
                  <CheckCircle2 className="size-3.5" />
                  {diff.resolved.length} fixed
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
            {diff.unchanged_count} problem{diff.unchanged_count === 1 ? "" : "s"} stayed the same. A problem counts
            as the same one when its title, file and scanner match, so the same problem in another file counts separately.
          </p>
        </section>
      ) : null}

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.35fr)_360px]">
        <SectionCard
          title="Problems found"
          description="Search and filter what this scan found. Checks that could not run are listed separately, not as problems."
        >
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_180px_180px]">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(event) => updateFilter("q", event.target.value)}
                  className="pl-9"
                  placeholder="Search problems, tools or files"
                  aria-label="Search problems"
                />
              </div>
              <Select
                aria-label="Filter problems by how serious they are"
                value={severityFilter}
                onChange={(event) => updateFilter("severity", event.target.value)}
              >
                <option value="all">Any severity</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
                <option value="info">Info</option>
              </Select>
              <Select
                aria-label="Filter problems by status"
                value={triageFilter}
                onChange={(event) => updateFilter("triage", event.target.value)}
              >
                <option value="all">Any status</option>
                <option value="open">{TRIAGE_LABELS.open}</option>
                <option value="fixed">{TRIAGE_LABELS.fixed}</option>
                <option value="false_positive">{TRIAGE_LABELS.false_positive}</option>
              </Select>
            </div>

            {filteredFindings.length === 0 ? (
              <EmptyState
                title={activeFindings.length === 0 ? "No problems found in the checks that finished" : "No problems match this search"}
                body={
                  activeFindings.length === 0
                    ? "That does not mean it is safe. Look at which checks finished before you trust this result."
                    : "Change the search or the filters to see more."
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
                            {/* One card per rule verdict, with the count, not
                                one card per affected tool. Five tools missing
                                a timeout is one thing to fix. */}
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
                          {finding.plain ? <p className="text-sm">{finding.plain.problem}</p> : null}
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
                              <span className="uppercase tracking-[0.12em]">Tools with the problem</span>{" "}
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
                              <span className="uppercase tracking-[0.12em]">What we found</span>{" "}
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
                              AI second opinion: may not be a real problem
                            </p>
                          ) : finding.llm_severity && finding.llm_severity !== finding.severity ? (
                            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                              <Sparkles className="size-3" />
                              AI second opinion suggests {finding.llm_severity}
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
            title="What we could check"
            description="Checks that were skipped or did not finish stay listed here, so the score is not mistaken for a full check."
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
                      <span className="text-sm text-muted-foreground">{STAGE_STATUS_LABELS[stage.status]}</span>
                    </div>
                    {stage.error ? (
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">{stage.error}</p>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </SectionCard>

          {/* This panel described a scoring model Aevrin stopped using when the
              engine replaced it: 100 minus severity weights, so higher was
              better. Risk now counts the other way and Aevrin does not compute
              it at all. Publishing the old direction under the word "current"
              inverted the meaning of every number on this page. */}
          <SectionCard title="How the grade works" description="Where the risk score and the grade come from.">
            <div className="space-y-3 text-sm leading-6 text-muted-foreground">
              <p>The scanner gives each tool a risk score and a letter. The risk score goes up with risk: 0 means no problems found, and 100 means do not use it. Aevrin does not change either number.</p>
              <p>A server gets the grade of its worst tool, not an average. You install the whole server, so one tool that can run code is not made safe by four that cannot.</p>
              <p>If the scan could not read a server&apos;s tools, it gets no grade at all, not a kind one. A grade has to be backed by what we actually checked.</p>
              <p>Marking a problem as fixed changes the counts and what the hook allows, but keeps the score the scan gave, so the report reads the same in the CLI and here.</p>
              <p>A good score never promises safety. Always look at which checks finished.</p>
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
