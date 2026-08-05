"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, CircleDashed, Loader2, MinusCircle, Search, Wrench, XCircle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Finding, Scan, ScanStage, Severity } from "@/lib/types";
import { OWASP_CATEGORY_LABELS, STAGE_LABELS, STAGE_ORDER } from "@/lib/types";
import {
  formatDateTime,
  formatDuration,
  summarizeCoverage,
  summarizeFindings,
  SCAN_SOURCE_LABELS,
  TARGET_TYPE_LABELS,
  verdictLabel,
} from "@/lib/presentation";
import { PageHeader, SectionCard, EmptyState } from "@/components/product-ui";
import { StatusBadge } from "@/components/status-badge";
import { SeverityBadge } from "@/components/severity-badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

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
  const [fixingAll, setFixingAll] = useState(false);
  const [fixingId, setFixingId] = useState<string | null>(null);
  const [canExport, setCanExport] = useState<boolean | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const [scanData, stagesData] = await Promise.all([api.getScan(scanId), api.getScanStages(scanId)]);
      setScan(scanData);
      setStages(stagesData);
      setLoadError(null);

      if (scanData.status === "completed" || scanData.status === "incomplete" || scanData.status === "failed") {
        const findingsData = await api.getScanFindings(scanId);
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
    api.getSubscription().then((subscription) => {
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
  const limitations = findings.filter((finding) => finding.not_tested);
  const resultSummary = verdictLabel(scan, counts);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Scan result"
        description="Review the target, actual coverage, score, urgent findings, and the limitations that still need separate verification."
        actions={
          <>
            {/* Whole-scan Fix It. Only offered for repository scans, since
                there is nothing to open a pull request against otherwise —
                but never hidden on plan grounds: it explains what's needed
                when pressed, the same as the per-finding button. */}
            {scan.target_type === "github_repo" && (scan.status === "completed" || scan.status === "incomplete") ? (
              <Button
                disabled={fixingAll}
                onClick={async () => {
                  setFixingAll(true);
                  try {
                    const result = await api.fixScan(scanId);
                    if (result.fixed > 0) {
                      toast.success(`Fix It: ${result.message}`);
                      void load();
                    } else {
                      toast.info(`Fix It: ${result.message}`);
                    }
                  } catch (err) {
                    toast.error(err instanceof ApiError ? err.message : "Could not run Fix It for this scan.");
                  } finally {
                    setFixingAll(false);
                  }
                }}
              >
                <Wrench className="size-4" />
                {fixingAll ? "Fixing all…" : "Fix all"}
              </Button>
            ) : null}
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
                    const { url } = await api.exportReport(scanId);
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
            <p className="max-w-3xl text-sm leading-6 text-muted-foreground">{resultSummary}</p>

            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <MetaBlock label="Scanned at" value={formatDateTime(scan.completed_at ?? scan.created_at)} />
              <MetaBlock label="Duration" value={formatDuration(scan.created_at, scan.completed_at)} />
              <MetaBlock label="Score" value={scan.score === null ? "Not available" : `${scan.score}/100`} />
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

      {scan.status === "incomplete" ? (
        <Alert variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>Partial scan coverage</AlertTitle>
          <AlertDescription>
            Required scanners did not complete for {scan.unreliable_stages.map((stage) => STAGE_LABELS[stage]).join(", ")}. The score reflects only the checks that actually ran.
          </AlertDescription>
        </Alert>
      ) : null}

      {scan.status === "failed" ? (
        <Alert variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>Scan failed</AlertTitle>
          <AlertDescription>
            This scan did not complete. Any results below are not a reliable assessment of this target — rescan before making a decision.
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
              <select
                aria-label="Filter findings by severity"
                className="h-9 rounded-lg border border-border bg-background px-3 text-sm"
                value={severityFilter}
                onChange={(event) => updateFilter("severity", event.target.value)}
              >
                <option value="all">All severities</option>
                <option value="critical">Critical</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
                <option value="info">Info</option>
              </select>
              <select
                aria-label="Filter findings by triage status"
                className="h-9 rounded-lg border border-border bg-background px-3 text-sm"
                value={triageFilter}
                onChange={(event) => updateFilter("triage", event.target.value)}
              >
                <option value="all">All statuses</option>
                <option value="open">Open</option>
                <option value="fixed">Fixed</option>
                <option value="false_positive">False positive</option>
              </select>
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

                  // A per-row Fix It can't live inside the row button — nesting
                  // buttons is invalid and breaks keyboard semantics — so the
                  // row is a container with the navigation button and the fix
                  // action as siblings.
                  const alreadyFixed = finding.autofix_status === "fixed" && finding.autofix_pr_url;
                  // Mirrors is_autofix_eligible server-side: a patch needs a
                  // single concrete file to rewrite. Dependency CVEs and
                  // manifest-only findings genuinely can't be patched this
                  // way, so offering the action there would only ever fail.
                  const fixable =
                    !finding.not_tested && !finding.excluded_path && Boolean(finding.file_path);

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
                            {finding.in_kev ? (
                              <span className="rounded-full border border-red-500/40 bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-600 dark:text-red-400">
                                KEV
                              </span>
                            ) : null}
                            {finding.epss_score !== null ? (
                              <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
                                EPSS {(finding.epss_score * 100).toFixed(finding.epss_score < 0.01 ? 2 : 0)}%
                              </span>
                            ) : null}
                            <span className="text-sm text-muted-foreground">
                              {OWASP_CATEGORY_LABELS[finding.owasp_category] ?? finding.owasp_category}
                            </span>
                          </div>
                          <p className="text-base font-medium">{finding.title}</p>
                          <p className="text-sm leading-6 text-muted-foreground line-clamp-2">
                            {finding.description}
                          </p>
                        </div>
                        <div className="space-y-1 text-right text-sm text-muted-foreground">
                          <div>{finding.tool}</div>
                          <div>{finding.file_path ? `${finding.file_path}${finding.line_start ? `:${finding.line_start}` : ""}` : finding.manifest_field ?? "Location unavailable"}</div>
                        </div>
                      </div>
                    </button>

                      {alreadyFixed ? (
                        <a
                          href={finding.autofix_pr_url ?? "#"}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={buttonVariants({ variant: "outline", size: "sm", className: "mt-4 mr-4 shrink-0" })}
                        >
                          View PR
                        </a>
                      ) : fixable ? (
                        <Button
                          variant="outline"
                          size="sm"
                          className="mt-4 mr-4 shrink-0"
                          disabled={fixingId === finding.id}
                          onClick={async () => {
                            setFixingId(finding.id);
                            try {
                              const result = await api.fixFinding(finding.id);
                              if (result.status === "fixed" && result.pr_url) {
                                toast.success("Fix It opened a draft pull request.");
                                void load();
                              } else if (result.status === "needs_github_connection") {
                                toast.error("Connect GitHub to let Fix It open pull requests.");
                              } else {
                                toast.error(result.failure_reason ?? "Could not fix this finding automatically.");
                              }
                            } catch (err) {
                              toast.error(err instanceof ApiError ? err.message : "Could not run Fix It.");
                            } finally {
                              setFixingId(null);
                            }
                          }}
                        >
                          <Wrench className="size-3.5" />
                          {fixingId === finding.id ? "Fixing…" : "Fix It"}
                        </Button>
                      ) : null}
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

          {excludedPathFindings.length > 0 ? (
            <Alert>
              <AlertTriangle className="size-4" />
              <AlertTitle>{excludedPathFindings.length} finding(s) excluded from the score</AlertTitle>
              <AlertDescription>
                These matched a test or fixture path convention (a <code>fixtures/</code>-style directory, or a
                filename like <code>*.test.ts</code>) and are hidden from the results above and excluded from
                scoring — sample code deliberately written to look vulnerable is not a real issue in the shipped
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
