"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, ArrowRight, Check, ScanSearch, TerminalSquare } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Finding, Scan, ScanStage } from "@/lib/types";
import { formatDate, formatDateTime, summarizeCoverage, summarizeFindings, uniqueTargets } from "@/lib/presentation";
import { ScoreGauge, SeverityDonut, SeverityTrendChart, type TrendPoint } from "@/components/dashboard-charts";
import { PageHeader, SectionCard } from "@/components/product-ui";
import { StatusBadge } from "@/components/status-badge";
import { UsageMeters } from "@/components/usage-meters";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

type ScanSummary = {
  scan: Scan;
  findings: Finding[];
  stages: ScanStage[];
};

export default function DashboardPage() {
  const router = useRouter();
  const [summaries, setSummaries] = useState<ScanSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [githubConnected, setGithubConnected] = useState<boolean | null>(null);

  // Only used by the first-use checklist. Failure just leaves the step in its
  // "not done" state rather than surfacing an error on the whole overview.
  useEffect(() => {
    let cancelled = false;
    api
      .getGithubStatus()
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

  // Oldest → newest, capped at 12 columns. Beyond that the bars get too thin
  // to read and the chart stops being a summary.
  const trend = useMemo<TrendPoint[]>(() => {
    if (!summaries) return [];
    return [...summaries]
      .sort((a, b) => new Date(a.scan.created_at).getTime() - new Date(b.scan.created_at).getTime())
      .slice(-12)
      .map((summary) => ({
        id: summary.scan.id,
        label: formatDate(summary.scan.completed_at ?? summary.scan.created_at),
        counts: summarizeFindings(
          summary.findings.filter((f) => !f.not_tested && !f.excluded_path && f.triage_status === "open"),
        ),
      }));
  }, [summaries]);

  // Everything below is derived from findings already loaded above — no extra
  // requests, and nothing displayed that isn't a real stored record.
  const insights = useMemo(() => {
    if (!summaries) return null;

    const openFindings = summaries.flatMap((summary) =>
      summary.findings
        .filter((f) => !f.not_tested && !f.excluded_path && f.triage_status === "open")
        .map((finding) => ({ finding, scan: summary.scan })),
    );

    const severityRank: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
    const topFindings = [...openFindings]
      .sort((a, b) => {
        const bySeverity = severityRank[a.finding.severity] - severityRank[b.finding.severity];
        if (bySeverity !== 0) return bySeverity;
        return new Date(b.scan.created_at).getTime() - new Date(a.scan.created_at).getTime();
      })
      .slice(0, 5);

    const byTarget = new Map<string, { target: string; scanId: string; critical: number; high: number; total: number }>();
    for (const { finding, scan } of openFindings) {
      const entry = byTarget.get(scan.target) ?? { target: scan.target, scanId: scan.id, critical: 0, high: 0, total: 0 };
      entry.total += 1;
      if (finding.severity === "critical") entry.critical += 1;
      if (finding.severity === "high") entry.high += 1;
      byTarget.set(scan.target, entry);
    }
    const topTargets = [...byTarget.values()]
      .sort((a, b) => b.critical - a.critical || b.high - a.high || b.total - a.total)
      .slice(0, 5);

    const counts = summarizeFindings(openFindings.map((entry) => entry.finding));
    const breakdownTotal = counts.critical + counts.high + counts.medium + counts.low;

    return { topFindings, topTargets, counts, breakdownTotal, openTotal: openFindings.length };
  }, [summaries]);

  if (summaries === null) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-24 w-full rounded-xl" />
        <div className="grid gap-4 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-36 w-full rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-96 w-full rounded-xl" />
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
        {/* First-use view: an actionable checklist reflecting real account
            state, not a wall of zero metrics. Steps that are genuinely done
            show as done; the rest each carry exactly one next action. */}
        <div className="grid items-start gap-6 xl:grid-cols-[1.35fr_0.9fr]">
          <SectionCard
            title="Finish setting up"
            description="Three steps to a first real result. You can do them in any order."
          >
            <ol className="flex flex-col">
              <SetupStep
                index={1}
                done
                title="Account created"
                body="You're signed in and on the Free plan."
              />
              <SetupStep
                index={2}
                done={githubConnected === true}
                loading={githubConnected === null}
                title="Connect GitHub"
                body="Adds private-repository scanning and lets Fix It open pull requests. Optional — public repos, live servers, and pasted configs work without it."
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

            <div className="mt-5 grid gap-3 border-t border-border pt-5 sm:grid-cols-2">
              <QuickActionCard
                title="Install the CLI"
                body="Scan from your terminal and wire Aevrin into CI."
                href="/integrations"
                icon={<TerminalSquare className="size-5 text-brand-text" />}
              />
              <QuickActionCard
                title="Add the Claude Code hook"
                body="Block or warn on unsafe MCP installs before they land."
                href="/integrations"
                icon={<ScanSearch className="size-5 text-brand-text" />}
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
            <Button nativeButton={false} render={<Link href="/integrations" />} variant="outline">CLI and hook setup</Button>
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
          <AlertDescription>
            {error} Existing scan records are still shown below.
          </AlertDescription>
        </Alert>
      ) : null}

      {/* One 3-column rhythm for the entire page: every row is either 2+1 or
          a single full-width panel on the same tracks. The previous version
          mixed 5-col, 3-col, and 1.4fr/0.92fr ratios, which is what made the
          modules read as scattered rather than composed. `panel-rise` staggers
          the whole page in on mount. */}
      <div className="panel-rise grid gap-3 lg:grid-cols-3">
        {/* Posture: the two questions you open this page for — how bad is the
            latest result, and is it getting better or worse. */}
        <Panel
          className="lg:col-span-2"
          style={{ "--i": 0 } as React.CSSProperties}
          title="Security posture"
          subtitle="Latest score, and open findings per scan over time."
          action={
            metrics?.latest ? (
              <Link
                href={`/scans/${metrics.latest.id}`}
                className="text-[11px] text-muted-foreground transition-colors hover:text-foreground"
              >
                Latest scan →
              </Link>
            ) : null
          }
        >
          <div className="@container h-full">
            <div className="grid h-full @2xl:grid-cols-[auto_1fr] @2xl:divide-x divide-border">
              <div className="flex flex-col items-center justify-center gap-3 border-b border-border px-6 py-5 @2xl:border-b-0">
                <ScoreGauge score={metrics?.latest?.score ?? null} />
                {metrics?.latest ? (
                  <div className="max-w-[180px] text-center">
                    <p className="truncate text-[12px] text-foreground">
                      {metrics.latest.target.replace(/^https?:\/\//, "")}
                    </p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {metrics.latest.status === "incomplete" ? "Partial coverage · " : ""}
                      {formatDate(metrics.latest.completed_at ?? metrics.latest.created_at)}
                    </p>
                  </div>
                ) : null}
              </div>

              <div className="flex min-w-0 flex-col justify-center">
                {trend.length > 0 ? (
                  <SeverityTrendChart points={trend} />
                ) : (
                  <p className="px-4 py-10 text-center text-[13px] text-muted-foreground">
                    No completed scans yet.
                  </p>
                )}
              </div>
            </div>
          </div>
        </Panel>

        {/* Open findings: the split, then the same numbers as text. */}
        <Panel
          style={{ "--i": 1 } as React.CSSProperties}
          title="Open findings"
          subtitle="Across every target, excluding triaged and untested."
        >
          {insights && insights.breakdownTotal > 0 ? (
            <div className="flex flex-col items-center gap-4 px-4 py-5">
              <SeverityDonut counts={insights.counts} total={insights.breakdownTotal} />
              <dl className="w-full space-y-2">
                {(
                  [
                    ["Critical", insights.counts.critical, "bg-severity-critical"],
                    ["High", insights.counts.high, "bg-severity-high"],
                    ["Medium", insights.counts.medium, "bg-severity-medium"],
                    ["Low", insights.counts.low, "bg-severity-low"],
                  ] as const
                ).map(([label, value, dot]) => (
                  <div key={label} className="flex items-center justify-between text-[12px]">
                    <dt className="flex items-center gap-2 text-muted-foreground">
                      <span aria-hidden="true" className={`size-1.5 rounded-full ${dot}`} />
                      {label}
                    </dt>
                    <dd className="tabular-nums text-foreground">{value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : (
            <p className="px-4 py-10 text-center text-[13px] text-muted-foreground">
              Nothing open right now.
            </p>
          )}
        </Panel>

        {/* Stat strip, spanning the full width so it separates the two halves
            of the page rather than floating above them. */}
        {metrics ? (
          <div
            className="@container lg:col-span-3 rounded-xl border border-border bg-card"
            style={{ "--i": 2 } as React.CSSProperties}
          >
            <dl className="grid grid-cols-2 divide-border @2xl:grid-cols-4 @2xl:divide-x">
              <Stat
                label="Critical"
                value={metrics.critical}
                detail="Open findings"
                tone={metrics.critical > 0 ? "critical" : undefined}
              />
              <Stat
                label="High"
                value={metrics.high}
                detail="Open findings"
                tone={metrics.high > 0 ? "high" : undefined}
              />
              <Stat label="Needs attention" value={metrics.attention} detail="Failed or partial scans" />
              <Stat label="Targets" value={metrics.targets} detail="Repos, servers, configs" />
            </dl>
          </div>
        ) : null}

        <Panel
          className="lg:col-span-2"
          style={{ "--i": 3 } as React.CSSProperties}
          title="Needs attention"
          subtitle="Highest severity first, across every scan."
          action={
            <Link
              href="/scans/history"
              className="text-[11px] text-muted-foreground transition-colors hover:text-foreground"
            >
              View all →
            </Link>
          }
        >
          {insights && insights.topFindings.length > 0 ? (
            <ul>
              {insights.topFindings.map(({ finding, scan }) => (
                <li key={finding.id}>
                  <Link
                    href={`/scans/${scan.id}/findings/${finding.id}`}
                    className="group flex items-center gap-3 border-b border-border px-4 py-3 transition-colors last:border-0 hover:bg-muted/40"
                  >
                    <SeverityDot severity={finding.severity} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] text-foreground">{finding.title}</span>
                      <span className="mt-0.5 block truncate font-mono text-[11px] text-muted-foreground">
                        {finding.file_path ? `${finding.file_path} · ` : ""}
                        {scan.target.replace(/^https?:\/\//, "")}
                      </span>
                    </span>
                    <ArrowRight className="size-3.5 shrink-0 text-muted-foreground transition-all group-hover:translate-x-0.5 group-hover:text-brand-text" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-4 py-8 text-center text-[13px] text-muted-foreground">
              No open critical or high findings. Coverage still matters — check the scans below.
            </p>
          )}
        </Panel>

        <div style={{ "--i": 4 } as React.CSSProperties}>
          <UsageMeters />
        </div>

        <Panel
          className="lg:col-span-3"
          style={{ "--i": 5 } as React.CSSProperties}
          title="Recent scans"
          subtitle="Target, coverage, and the score each scan actually produced."
          action={
            <Link
              href="/scans/history"
              className="text-[11px] text-muted-foreground transition-colors hover:text-foreground"
            >
              View all →
            </Link>
          }
        >
          <ul>
            {summaries.slice(0, 6).map((summary) => (
              <li key={summary.scan.id}>
                <ScanRow summary={summary} />
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}

/** One cell of the top stat strip. Deliberately borderless — the strip's
 *  container and divide-x supply the structure, so these read as one related
 *  set instead of five competing widgets. */
function Stat({
  label,
  value,
  suffix,
  detail,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  suffix?: string;
  detail?: string;
  tone?: "critical" | "high";
}) {
  const valueTone =
    tone === "critical" ? "text-severity-critical" : tone === "high" ? "text-severity-high" : "text-foreground";

  return (
    <div className="border-b border-border px-4 py-3.5 last:border-b-0 @2xl:border-b-0">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="mt-1.5">
        <span className="flex items-baseline gap-1.5">
          <span className={`text-2xl font-semibold tracking-tight tabular-nums ${valueTone}`}>{value}</span>
          {suffix ? <span className="text-xs text-muted-foreground">{suffix}</span> : null}
        </span>
        {detail ? <span className="mt-0.5 block text-xs text-muted-foreground">{detail}</span> : null}
      </dd>
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
    <li className="flex items-start gap-3 border-b border-border py-4 last:border-0">
      <span
        aria-hidden="true"
        className={
          done
            ? "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-foreground text-background"
            : "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-border text-[11px] text-muted-foreground"
        }
      >
        {done ? <Check className="size-3" /> : index}
      </span>
      <div className="min-w-0 flex-1">
        <p className={done ? "text-sm font-medium text-muted-foreground line-through" : "text-sm font-medium text-foreground"}>
          {title}
          <span className="sr-only">{done ? " — done" : " — not done yet"}</span>
        </p>
        <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{body}</p>
      </div>
      {loading ? null : <div className="shrink-0">{action}</div>}
    </li>
  );
}

/** The dashboard's single container primitive. Everything on the page is a
 *  Panel, so headers, borders, and padding are identical everywhere — the
 *  page previously mixed three card styles with different header treatments,
 *  which is most of why it read as assembled rather than designed. Rows
 *  supply their own horizontal padding so list items span edge-to-edge on
 *  hover. */
function Panel({
  title,
  subtitle,
  action,
  children,
  className,
  style,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <section
      style={style}
      className={cn("flex flex-col overflow-hidden rounded-xl border border-border bg-card", className)}
    >
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-[13px] font-medium text-foreground">{title}</h2>
          {subtitle ? <p className="mt-0.5 text-[11px] text-muted-foreground">{subtitle}</p> : null}
        </div>
        {action ? <div className="shrink-0 pt-0.5">{action}</div> : null}
      </div>
      <div className="flex-1">{children}</div>
    </section>
  );
}

/** Compact scan row — status, target, coverage, and score on one line. The
 *  previous version was a three-column grid card with eight labelled fields;
 *  at six rows that turned the page into a wall of text. */
function ScanRow({ summary }: { summary: ScanSummary }) {
  const counts = summarizeFindings(
    summary.findings.filter((f) => !f.not_tested && !f.excluded_path && f.triage_status === "open"),
  );
  const coverage = summarizeCoverage(summary.stages);
  const total = summary.stages.length || 6;

  return (
    <Link
      href={`/scans/${summary.scan.id}`}
      className="group flex items-center gap-3 border-b border-border px-4 py-3 transition-colors last:border-0 hover:bg-muted/40"
    >
      <StatusBadge status={summary.scan.status} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] text-foreground">
          {summary.scan.target.replace(/^https?:\/\//, "")}
        </span>
        <span className="mt-0.5 block text-[11px] text-muted-foreground">
          {coverage.completed}/{total} stages · {formatDateTime(summary.scan.completed_at ?? summary.scan.created_at)}
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-3">
        {counts.critical > 0 ? (
          <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <span className="size-1.5 rounded-full bg-severity-critical" aria-hidden="true" />
            {counts.critical}
          </span>
        ) : null}
        {counts.high > 0 ? (
          <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <span className="size-1.5 rounded-full bg-severity-high" aria-hidden="true" />
            {counts.high}
          </span>
        ) : null}
        <span className="w-10 text-right text-[13px] font-medium tabular-nums text-foreground">
          {summary.scan.score ?? "—"}
        </span>
      </span>
    </Link>
  );
}

/** Severity shown as a colored dot *plus* its label — never color alone, so
 *  it stays readable for colorblind users and in screen readers. */
function SeverityDot({ severity }: { severity: Finding["severity"] }) {
  const dotClass =
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
    <span className="flex shrink-0 items-center gap-1.5 text-[11px] text-muted-foreground capitalize">
      <span className={`size-1.5 rounded-full ${dotClass}`} aria-hidden="true" />
      {severity}
    </span>
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
      className="rounded-xl border border-border bg-background/80 p-4 transition-colors hover:bg-muted/40"
    >
      <div className="space-y-3">
        <div className="flex items-center gap-3">{icon}<span className="font-medium">{title}</span></div>
        <p className="text-sm leading-6 text-muted-foreground">{body}</p>
      </div>
    </Link>
  );
}

