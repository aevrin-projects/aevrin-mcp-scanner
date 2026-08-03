"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowRight, Clock3, ScanSearch, TerminalSquare } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Finding, Scan, ScanStage } from "@/lib/types";
import { SCAN_SOURCE_LABELS, TARGET_TYPE_LABELS, formatDateTime, formatDuration, summarizeCoverage, summarizeFindings, uniqueTargets, verdictLabel } from "@/lib/presentation";
import { PageHeader, MetricCard, SectionCard, EmptyState } from "@/components/product-ui";
import { StatusBadge } from "@/components/status-badge";
import { SeverityBadge } from "@/components/severity-badge";
import { UsageMeters } from "@/components/usage-meters";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

type ScanSummary = {
  scan: Scan;
  findings: Finding[];
  stages: ScanStage[];
};

export default function DashboardPage() {
  const router = useRouter();
  const [summaries, setSummaries] = useState<ScanSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
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
          setSummaries([]);
          setError(err instanceof ApiError ? err.message : "Could not load the overview.");
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const metrics = useMemo(() => {
    if (!summaries) return null;

    let critical = 0;
    let high = 0;
    let attention = 0;

    for (const summary of summaries) {
      const activeFindings = summary.findings.filter((finding) => !finding.not_tested && finding.triage_status === "open");
      const findingCounts = summarizeFindings(activeFindings);
      critical += findingCounts.critical;
      high += findingCounts.high;

      if (
        summary.scan.status === "failed" ||
        summary.scan.status === "incomplete" ||
        findingCounts.critical > 0 ||
        findingCounts.high > 0
      ) {
        attention += 1;
      }
    }

    return {
      critical,
      high,
      attention,
      latest: summaries[0]?.scan ?? null,
      targets: uniqueTargets(summaries.map((summary) => summary.scan)),
    };
  }, [summaries]);

  if (summaries === null) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-24 w-full rounded-3xl" />
        <div className="grid gap-4 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-36 w-full rounded-3xl" />
          ))}
        </div>
        <Skeleton className="h-96 w-full rounded-3xl" />
      </div>
    );
  }

  if (summaries.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Overview"
          description="See what needs attention first, what your latest scan actually covered, and which setup path to take next."
          actions={
            <Button onClick={() => router.push("/scans/new")}>
              Scan an MCP server
              <ArrowRight className="size-4" />
            </Button>
          }
        />
        {error ? (
          <Alert variant="destructive">
            <AlertTriangle className="size-4" />
            <AlertTitle>Could not load overview data</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        <EmptyState
          title="Start with one real scan"
          body="Scan a GitHub repository, a live MCP server, or a pasted MCP configuration. GitHub scans provide the broadest source, secret, and dependency coverage."
          actionLabel="New scan"
          onAction={() => router.push("/scans/new")}
        />
        <div className="grid gap-6 xl:grid-cols-[1.35fr_0.9fr]">
          <SectionCard
            title="Getting started"
            description="Choose the path that matches how you evaluate servers today."
          >
            <div className="grid gap-4 md:grid-cols-3">
              <QuickActionCard
                title="Dashboard scan"
                body="Run a browser-based scan against a repo, live server, or pasted config."
                href="/scans/new"
                icon={<ScanSearch className="size-5 text-brand-text" />}
              />
              <QuickActionCard
                title="CLI setup"
                body="Install the CLI, sign in with device flow, and run your first local scan."
                href="/integrations"
                icon={<TerminalSquare className="size-5 text-brand-text" />}
              />
              <QuickActionCard
                title="Claude Code hook"
                body="Add pre-install checks so unsafe MCP adds get blocked or warned."
                href="/integrations"
                icon={<Clock3 className="size-5 text-brand-text" />}
              />
            </div>
          </SectionCard>
          <UsageMeters />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        description="Prioritize urgent findings, partial coverage, and the latest scan outcome before you install or approve an MCP server."
        actions={
          <>
            <Button render={<Link href="/integrations" />} variant="outline">CLI and hook setup</Button>
            <Button render={<Link href="/scans/new" />}>
              New scan
              <ArrowRight className="size-4" />
            </Button>
          </>
        }
      />

      {error ? (
        <Alert variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>Could not refresh all overview data</AlertTitle>
          <AlertDescription>
            {error} Existing scan records are still shown below.
          </AlertDescription>
        </Alert>
      ) : null}

      {metrics ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Active critical findings"
            value={metrics.critical}
            detail="Open findings across the latest 25 scans."
            tone={metrics.critical > 0 ? "critical" : "default"}
          />
          <MetricCard
            label="Active high findings"
            value={metrics.high}
            detail="Open high-severity findings across the latest 25 scans."
            tone={metrics.high > 0 ? "high" : "default"}
          />
          <MetricCard
            label="Scans requiring attention"
            value={metrics.attention}
            detail="Failed, partial, or urgent-result scans."
            tone={metrics.attention > 0 ? "high" : "default"}
          />
          <MetricCard
            label="Targets scanned"
            value={metrics.targets}
            detail={
              metrics.latest
                ? `Latest status: ${metrics.latest.status === "incomplete" ? "partial" : metrics.latest.status}`
                : "No completed scans yet"
            }
            tone={metrics.targets > 0 ? "success" : "default"}
          />
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.4fr_0.92fr]">
        <SectionCard
          title="Needs attention"
          description="Ordered by scan reliability, severity, and recency."
          action={
            <Button render={<Link href="/scans/history" />} variant="outline" size="sm">
              View history
            </Button>
          }
        >
          <div className="space-y-3">
            {summaries
              .filter((summary) => {
                const counts = summarizeFindings(
                  summary.findings.filter((finding) => !finding.not_tested && finding.triage_status === "open"),
                );
                return (
                  summary.scan.status === "failed" ||
                  summary.scan.status === "incomplete" ||
                  counts.critical > 0 ||
                  counts.high > 0
                );
              })
              .slice(0, 6)
              .map((summary) => (
                <AttentionRow key={summary.scan.id} summary={summary} />
              ))}
          </div>
        </SectionCard>

        <div className="space-y-6">
          <UsageMeters />
          <SectionCard
            title="Quick actions"
            description="Use the path that matches how you scan today."
          >
            <div className="grid gap-3">
              <QuickActionCard
                title="Run a new dashboard scan"
                body="Choose GitHub, live server, or pasted config input."
                href="/scans/new"
                icon={<ScanSearch className="size-5 text-brand-text" />}
              />
              <QuickActionCard
                title="Set up the CLI"
                body="Install, sign in, and verify from your terminal."
                href="/integrations"
                icon={<TerminalSquare className="size-5 text-brand-text" />}
              />
            </div>
          </SectionCard>
        </div>
      </div>

      <SectionCard
        title="Recent scans"
        description="Includes the target, target type, duration, current verdict, and whether the scan completed fully."
      >
        <div className="space-y-3">
          {summaries.slice(0, 8).map((summary) => (
            <RecentScanRow key={summary.scan.id} summary={summary} />
          ))}
        </div>
      </SectionCard>
    </div>
  );
}

function QuickActionCard({
  title,
  body,
  href,
  icon,
}: {
  title: string;
  body: string;
  href: string;
  icon: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="rounded-2xl border border-border bg-background/80 p-4 transition-colors hover:bg-muted/40"
    >
      <div className="space-y-3">
        <div className="flex items-center gap-3">{icon}<span className="font-medium">{title}</span></div>
        <p className="text-sm leading-6 text-muted-foreground">{body}</p>
      </div>
    </Link>
  );
}

function AttentionRow({ summary }: { summary: ScanSummary }) {
  const activeCounts = summarizeFindings(
    summary.findings.filter((finding) => !finding.not_tested && finding.triage_status === "open"),
  );
  const coverage = summarizeCoverage(summary.stages);

  return (
    <Link
      href={`/scans/${summary.scan.id}`}
      className="flex flex-col gap-4 rounded-2xl border border-border bg-background/80 p-4 transition-colors hover:bg-muted/30 lg:flex-row lg:items-center lg:justify-between"
    >
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={summary.scan.status} />
          <span className="text-sm text-muted-foreground">{TARGET_TYPE_LABELS[summary.scan.target_type]}</span>
          <span className="text-sm text-muted-foreground">{SCAN_SOURCE_LABELS[summary.scan.source]}</span>
        </div>
        <p className="break-all text-base font-medium text-foreground">{summary.scan.target}</p>
        <p className="text-sm leading-6 text-muted-foreground">
          {verdictLabel(summary.scan, activeCounts)}. Completed {coverage.completed} of {summary.stages.length || 6} stages.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        {activeCounts.critical > 0 ? (
          <span className="inline-flex items-center gap-2 rounded-full border border-severity-critical/40 bg-severity-critical/10 px-3 py-1 text-severity-critical">
            <SeverityBadge severity="critical" />
            {activeCounts.critical}
          </span>
        ) : null}
        {activeCounts.high > 0 ? (
          <span className="inline-flex items-center gap-2 rounded-full border border-severity-high/40 bg-severity-high/10 px-3 py-1 text-severity-high">
            <SeverityBadge severity="high" />
            {activeCounts.high}
          </span>
        ) : null}
        <span className="text-muted-foreground">{formatDateTime(summary.scan.completed_at ?? summary.scan.created_at)}</span>
      </div>
    </Link>
  );
}

function RecentScanRow({ summary }: { summary: ScanSummary }) {
  const activeCounts = summarizeFindings(
    summary.findings.filter((finding) => !finding.not_tested && finding.triage_status === "open"),
  );
  const coverage = summarizeCoverage(summary.stages);

  return (
    <Link
      href={`/scans/${summary.scan.id}`}
      className="grid gap-4 rounded-2xl border border-border bg-background/80 p-4 transition-colors hover:bg-muted/30 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_auto]"
    >
      <div className="space-y-2">
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
        <span>Active critical/high: {activeCounts.critical + activeCounts.high}</span>
        <span>Coverage: {coverage.completed}/{summary.stages.length || 6} stages complete</span>
      </div>

      <div className="flex items-center gap-2 text-sm">
        <div className="text-right">
          <div className="text-2xl font-semibold">{summary.scan.score ?? "—"}</div>
          <div className="text-xs text-muted-foreground">score</div>
        </div>
      </div>
    </Link>
  );
}
