"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ScanSearch,
  ShieldAlert,
  TerminalSquare,
} from "lucide-react";
import { ApiError } from "@/shared/api";
import { githubApi } from "@/entities/github";
import { findingApi, summarizeFindings, type Finding } from "@/entities/finding";
import {
  StatusBadge,
  scanApi,
  summarizeCoverage,
  uniqueTargets,
  type Scan,
  type ScanStage,
} from "@/entities/scan";
import { UsageMeters } from "@/entities/usage";
import { formatDate, formatDateTime } from "@/shared/lib/format";
import {
  EmptyState,
  IconTile,
  ListGroup,
  ListRow,
  Metric,
  PageHeader,
  Panel,
  PanelBody,
  PanelTableWrap,
  Progress,
  SectionCard,
  StatTile,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
} from "@/shared/ui";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { ScoreGauge, SeverityDonut, SeverityTrendChart, type TrendPoint } from "./dashboard-charts";

type ScanSummary = {
  scan: Scan;
  findings: Finding[];
  stages: ScanStage[];
};

const SEVERITY_RANK: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

/** Findings a person still has to act on: triaged and untested ones are
 *  records, not work. Every count on this page uses this one filter. */
function openFindings(findings: Finding[]) {
  return findings.filter((f) => !f.not_tested && !f.excluded_path && f.triage_status === "open");
}

export function DashboardPage() {
  const [summaries, setSummaries] = useState<ScanSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [githubConnected, setGithubConnected] = useState<boolean | null>(null);

  // Only used by the first-use checklist. Failure just leaves the step in its
  // "not done" state rather than surfacing an error on the whole overview.
  useEffect(() => {
    let cancelled = false;
    githubApi
      .getStatus()
      .then((status) => {
        if (!cancelled) setGithubConnected(status.connected);
      })
      .catch(() => {
        if (!cancelled) setGithubConnected(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const scans = await scanApi.listScans();
        const details = await Promise.all(
          scans.map(async (scan) => {
            const [findings, stages] = await Promise.all([
              findingApi.getScanFindings(scan.id).catch(() => []),
              scanApi.getScanStages(scan.id).catch(() => []),
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
      const counts = summarizeFindings(
        summary.findings.filter((f) => !f.not_tested && f.triage_status === "open"),
      );
      critical += counts.critical;
      high += counts.high;

      if (
        summary.scan.status === "failed" ||
        summary.scan.status === "incomplete" ||
        counts.critical > 0 ||
        counts.high > 0
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

  // Oldest to newest, capped at 12 columns. Beyond that the bars get too thin
  // to read and the chart stops being a summary.
  const trend = useMemo<TrendPoint[]>(() => {
    if (!summaries) return [];
    return [...summaries]
      .sort((a, b) => new Date(a.scan.created_at).getTime() - new Date(b.scan.created_at).getTime())
      .slice(-12)
      .map((summary) => ({
        id: summary.scan.id,
        label: formatDate(summary.scan.completed_at ?? summary.scan.created_at),
        counts: summarizeFindings(openFindings(summary.findings)),
      }));
  }, [summaries]);

  // Everything below is derived from findings already loaded above, no extra
  // requests, and nothing displayed that isn't a real stored record.
  const insights = useMemo(() => {
    if (!summaries) return null;

    const open = summaries.flatMap((summary) =>
      openFindings(summary.findings).map((finding) => ({ finding, scan: summary.scan })),
    );

    const topFindings = [...open]
      .sort(
        (a, b) =>
          SEVERITY_RANK[a.finding.severity] - SEVERITY_RANK[b.finding.severity] ||
          new Date(b.scan.created_at).getTime() - new Date(a.scan.created_at).getTime(),
      )
      .slice(0, 5);

    const byTarget = new Map<string, { target: string; scanId: string; critical: number; high: number; total: number }>();
    for (const { finding, scan } of open) {
      const entry =
        byTarget.get(scan.target) ?? { target: scan.target, scanId: scan.id, critical: 0, high: 0, total: 0 };
      entry.total += 1;
      if (finding.severity === "critical") entry.critical += 1;
      if (finding.severity === "high") entry.high += 1;
      byTarget.set(scan.target, entry);
    }
    const topTargets = [...byTarget.values()]
      .sort((a, b) => b.critical - a.critical || b.high - a.high || b.total - a.total)
      .slice(0, 5);

    const counts = summarizeFindings(open.map((entry) => entry.finding));
    const breakdownTotal = counts.critical + counts.high + counts.medium + counts.low;

    return { topFindings, topTargets, counts, breakdownTotal, openTotal: open.length };
  }, [summaries]);

  if (summaries === null) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-14 w-full rounded-lg" />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-[6.5rem] w-full rounded-lg" />
          ))}
        </div>
        <div className="grid gap-3 lg:grid-cols-3">
          <Skeleton className="h-80 w-full rounded-lg lg:col-span-2" />
          <Skeleton className="h-80 w-full rounded-lg" />
        </div>
      </div>
    );
  }

  if (summaries.length === 0) {
    return (
      <div className="space-y-5">
        <PageHeader
          pretitle="Overview"
          title="Dashboard"
          description="See what needs attention first, what your latest scan actually covered, and which setup path to take next."
          actions={
            <Button nativeButton={false} render={<Link href="/scans/new" />}>
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

        {/* First-use view: an actionable checklist reflecting real account
            state, not a wall of zero metrics. Steps that are genuinely done
            show as done; the rest each carry exactly one next action. */}
        <div className="grid items-start gap-3 xl:grid-cols-[1.35fr_0.9fr]">
          <SectionCard
            title="Finish setting up"
            description="Three steps to a first real result. You can do them in any order."
            flush
          >
            <ol className="divide-y divide-border">
              <SetupStep index={1} done title="Account created" body="You're signed in and on the Free plan." />
              <SetupStep
                index={2}
                done={githubConnected === true}
                loading={githubConnected === null}
                title="Connect GitHub"
                body="Adds private-repository scanning. Optional; public repos, live servers, and pasted configs work without it."
                action={
                  githubConnected === false ? (
                    <Button variant="outline" size="sm" nativeButton={false} render={<Link href="/settings/billing" />}>
                      Connect
                    </Button>
                  ) : null
                }
              />
              <SetupStep
                index={3}
                done={false}
                title="Run your first scan"
                body="Point Aevrin at a GitHub repository, a live MCP server, or a pasted mcp.json. Results land here when it finishes."
                action={
                  <Button size="sm" nativeButton={false} render={<Link href="/scans/new" />}>
                    New scan
                    <ArrowRight className="size-3.5" />
                  </Button>
                }
              />
            </ol>
            <div className="grid gap-3 border-t border-border p-5 sm:grid-cols-2">
              <StatTile
                icon={<TerminalSquare />}
                title={<Link href="/integrations">Install the CLI</Link>}
                subtitle="Scan from your terminal and wire Aevrin into CI."
              />
              <StatTile
                icon={<ScanSearch />}
                title={<Link href="/integrations">Add the Claude Code hook</Link>}
                subtitle="Block or warn on unsafe MCP installs before they land."
              />
            </div>
          </SectionCard>
          <UsageMeters />
        </div>
      </div>
    );
  }

  const latest = metrics?.latest ?? null;

  return (
    <div className="space-y-5">
      <PageHeader
        pretitle="Overview"
        title="Dashboard"
        description="Prioritize urgent findings, partial coverage, and the latest scan outcome before you install or approve an MCP server."
        actions={
          <>
            <Button nativeButton={false} render={<Link href="/integrations" />} variant="outline">
              CLI and hook setup
            </Button>
            <Button nativeButton={false} render={<Link href="/scans/new" />}>
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
          <AlertDescription>{error} Existing scan records are still shown below.</AlertDescription>
        </Alert>
      ) : null}

      {/* Tabler's stat row: four figures across the full width, each on its
          own panel so the row survives wrapping at every breakpoint instead
          of turning into a two-by-two grid of dividers. */}
      {metrics ? (
        <div className="panel-rise grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Panel className="px-5 py-4" style={{ "--i": 0 } as React.CSSProperties}>
            <Metric
              label="Critical"
              value={metrics.critical}
              detail="Open findings"
              tone={metrics.critical > 0 ? "critical" : "default"}
            />
          </Panel>
          <Panel className="px-5 py-4" style={{ "--i": 1 } as React.CSSProperties}>
            <Metric
              label="High"
              value={metrics.high}
              detail="Open findings"
              tone={metrics.high > 0 ? "high" : "default"}
            />
          </Panel>
          <Panel className="px-5 py-4" style={{ "--i": 2 } as React.CSSProperties}>
            <Metric label="Needs attention" value={metrics.attention} detail="Failed or partial scans" />
          </Panel>
          <Panel className="px-5 py-4" style={{ "--i": 3 } as React.CSSProperties}>
            <Metric label="Targets" value={metrics.targets} detail="Repos, servers, configs" />
          </Panel>
        </div>
      ) : null}

      <div className="panel-rise grid gap-3 lg:grid-cols-3">
        {/* Posture: the two questions you open this page for, how bad is the
            latest result, and is it getting better or worse. */}
        <SectionCard
          className="lg:col-span-2"
          style={{ "--i": 4 } as React.CSSProperties}
          title="Security posture"
          description="Latest score, and open findings per scan over time."
          action={
            latest ? (
              <Link
                href={`/scans/${latest.id}`}
                className="text-[13px] text-muted-foreground transition-colors hover:text-foreground"
              >
                Latest scan &rarr;
              </Link>
            ) : null
          }
          flush
        >
          <div className="@container h-full">
            <div className="grid h-full divide-border @2xl:grid-cols-[auto_1fr] @2xl:divide-x">
              <div className="flex flex-col items-center justify-center gap-3 border-b border-border px-6 py-5 @2xl:border-b-0">
                <ScoreGauge score={latest?.score ?? null} />
                {latest ? (
                  <div className="max-w-[180px] text-center">
                    <p className="truncate text-[13px]">{latest.target.replace(/^https?:\/\//, "")}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {latest.status === "incomplete" ? "Partial coverage · " : ""}
                      {formatDate(latest.completed_at ?? latest.created_at)}
                    </p>
                  </div>
                ) : null}
              </div>
              <div className="flex min-w-0 flex-col justify-center">
                {trend.length > 0 ? (
                  <SeverityTrendChart points={trend} />
                ) : (
                  <EmptyState title="No completed scans yet" body="Finished scans plot here as a severity trend." />
                )}
              </div>
            </div>
          </div>
        </SectionCard>

        {/* Open findings: the split, then the same numbers as text. */}
        <SectionCard
          style={{ "--i": 5 } as React.CSSProperties}
          title="Open findings"
          description="Across every target, excluding triaged and untested."
          flush
        >
          {insights && insights.breakdownTotal > 0 ? (
            <PanelBody className="flex flex-col items-center gap-5">
              <SeverityDonut counts={insights.counts} total={insights.breakdownTotal} />
              <dl className="w-full space-y-2.5">
                {(
                  [
                    ["Critical", insights.counts.critical, "bg-severity-critical"],
                    ["High", insights.counts.high, "bg-severity-high"],
                    ["Medium", insights.counts.medium, "bg-severity-medium"],
                    ["Low", insights.counts.low, "bg-severity-low"],
                  ] as const
                ).map(([label, value, dot]) => (
                  <div key={label} className="flex items-center justify-between text-[13px]">
                    <dt className="flex items-center gap-2 text-muted-foreground">
                      <span aria-hidden="true" className={`size-1.5 rounded-full ${dot}`} />
                      {label}
                    </dt>
                    <dd className="font-medium tabular-nums">{value}</dd>
                  </div>
                ))}
              </dl>
            </PanelBody>
          ) : (
            <EmptyState title="Nothing open right now" body="Every finding is triaged, fixed, or untested." />
          )}
        </SectionCard>

        <SectionCard
          className="lg:col-span-2"
          style={{ "--i": 6 } as React.CSSProperties}
          title="Needs attention"
          description="Highest severity first, across every scan."
          action={
            <Link
              href="/scans/history"
              className="text-[13px] text-muted-foreground transition-colors hover:text-foreground"
            >
              View all &rarr;
            </Link>
          }
          flush
        >
          {insights && insights.topFindings.length > 0 ? (
            <ListGroup>
              {insights.topFindings.map(({ finding, scan }) => (
                <ListRow
                  key={finding.id}
                  href={`/scans/${scan.id}/findings/${finding.id}`}
                  leading={<SeverityDot severity={finding.severity} />}
                  title={finding.title}
                  subtitle={
                    <span className="font-mono text-xs">
                      {finding.file_path ? `${finding.file_path} · ` : ""}
                      {scan.target.replace(/^https?:\/\//, "")}
                    </span>
                  }
                  trailing={<ArrowRight className="size-3.5 text-muted-foreground" />}
                />
              ))}
            </ListGroup>
          ) : (
            <EmptyState
              title="No open critical or high findings"
              body="Coverage still matters. Check what each recent scan actually reached below."
            />
          )}
        </SectionCard>

        <div style={{ "--i": 7 } as React.CSSProperties}>
          <UsageMeters />
        </div>

        {/* Riskiest targets: the same open findings, grouped by what they are
            attached to, so a repeatedly-failing repo is visible as one row
            rather than five scattered findings. */}
        {insights && insights.topTargets.length > 0 ? (
          <SectionCard
            style={{ "--i": 8 } as React.CSSProperties}
            title="Riskiest targets"
            description="Open findings grouped by what they were found in."
            flush
          >
            <ListGroup>
              {insights.topTargets.map((target) => (
                <ListRow
                  key={target.target}
                  href={`/scans/${target.scanId}`}
                  leading={
                    <IconTile tone={target.critical > 0 ? "critical" : target.high > 0 ? "high" : "default"}>
                      <ShieldAlert />
                    </IconTile>
                  }
                  title={target.target.replace(/^https?:\/\//, "")}
                  subtitle={`${target.total} open · ${target.critical} critical · ${target.high} high`}
                  trailing={
                    <span className="text-sm font-medium tabular-nums">{target.total}</span>
                  }
                />
              ))}
            </ListGroup>
          </SectionCard>
        ) : null}

        {/* Recent scans as a real table: with five columns of mixed types, a
            list row forces every value into a subtitle string, and coverage
            stops being comparable between rows. */}
        <SectionCard
          className={insights && insights.topTargets.length > 0 ? "lg:col-span-2" : "lg:col-span-3"}
          style={{ "--i": 9 } as React.CSSProperties}
          title="Recent scans"
          description="Target, coverage, and the score each scan actually produced."
          action={
            <Link
              href="/scans/history"
              className="text-[13px] text-muted-foreground transition-colors hover:text-foreground"
            >
              View all &rarr;
            </Link>
          }
          flush
        >
          <PanelTableWrap>
            <Table className="min-w-[42rem]">
              <THead>
                <TR className="hover:bg-transparent">
                  <TH>Target</TH>
                  <TH>Status</TH>
                  <TH className="w-40">Coverage</TH>
                  <TH>Open</TH>
                  <TH className="text-right">Score</TH>
                </TR>
              </THead>
              <TBody>
                {summaries.slice(0, 6).map((summary) => (
                  <ScanRow key={summary.scan.id} summary={summary} />
                ))}
              </TBody>
            </Table>
          </PanelTableWrap>
        </SectionCard>
      </div>
    </div>
  );
}

/** One row of the first-use setup checklist. `done` drives a filled check,
 *  `loading` covers the brief window before real account state resolves so a
 *  step never flashes "not done" and then flips. */
function SetupStep({
  index,
  title,
  body,
  done,
  loading = false,
  action,
}: {
  index: number;
  title: string;
  body: string;
  done: boolean;
  loading?: boolean;
  action?: React.ReactNode;
}) {
  return (
    <li className="flex items-start gap-3 px-5 py-4">
      <span
        aria-hidden="true"
        className={
          done
            ? "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-foreground text-background"
            : "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-input text-[11px] text-muted-foreground"
        }
      >
        {done ? <Check className="size-3" /> : index}
      </span>
      <div className="min-w-0 flex-1">
        <p className={done ? "text-sm font-medium text-muted-foreground line-through" : "text-sm font-medium"}>
          {title}
          <span className="sr-only">{done ? ": done" : ": not done yet"}</span>
        </p>
        <p className="mt-1 text-[13px] leading-5 text-muted-foreground">{body}</p>
      </div>
      {loading ? null : <div className="shrink-0">{action}</div>}
    </li>
  );
}

/** One scan as a table row. Coverage is a rail plus its own "4/6" label:
 *  the rail makes rows comparable at a glance, the label is the actual
 *  answer for anyone the rail does not reach. */
function ScanRow({ summary }: { summary: ScanSummary }) {
  const counts = summarizeFindings(openFindings(summary.findings));
  const coverage = summarizeCoverage(summary.stages);
  const total = summary.stages.length || 6;
  const target = summary.scan.target.replace(/^https?:\/\//, "");

  return (
    <TR>
      <TD className="max-w-[18rem]">
        <Link href={`/scans/${summary.scan.id}`} className="block truncate font-medium hover:underline">
          {target}
        </Link>
        <span className="mt-0.5 block text-xs text-muted-foreground">
          {formatDateTime(summary.scan.completed_at ?? summary.scan.created_at)}
        </span>
      </TD>
      <TD>
        <StatusBadge status={summary.scan.status} />
      </TD>
      <TD>
        <div className="flex items-center gap-2">
          <Progress
            className="w-20"
            value={total ? coverage.completed / total : 0}
            label={`Coverage for ${target}`}
            barClassName={coverage.failed > 0 ? "bg-severity-high" : "bg-brand"}
          />
          <span className="text-xs whitespace-nowrap text-muted-foreground tabular-nums">
            {coverage.completed}/{total}
          </span>
        </div>
      </TD>
      <TD>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {counts.critical > 0 ? (
            <span className="flex items-center gap-1">
              <span className="size-1.5 rounded-full bg-severity-critical" aria-hidden="true" />
              {counts.critical} critical
            </span>
          ) : null}
          {counts.high > 0 ? (
            <span className="flex items-center gap-1">
              <span className="size-1.5 rounded-full bg-severity-high" aria-hidden="true" />
              {counts.high} high
            </span>
          ) : null}
          {counts.critical === 0 && counts.high === 0 ? <span>None urgent</span> : null}
        </div>
      </TD>
      <TD className="text-right text-sm font-medium tabular-nums">{summary.scan.score ?? "-"}</TD>
    </TR>
  );
}

/** Severity as a coloured dot *plus* its label; never colour alone, so it
 *  stays readable for colourblind users and in screen readers. */
function SeverityDot({ severity }: { severity: Finding["severity"] }) {
  const dot =
    severity === "critical"
      ? "bg-severity-critical"
      : severity === "high"
        ? "bg-severity-high"
        : severity === "medium"
          ? "bg-severity-medium"
          : severity === "low"
            ? "bg-severity-low"
            : "bg-muted-foreground";

  return (
    <span className="flex w-16 shrink-0 items-center gap-1.5 text-xs text-muted-foreground capitalize">
      <span className={`size-1.5 rounded-full ${dot}`} aria-hidden="true" />
      {severity}
    </span>
  );
}

