"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Activity, CalendarClock, ExternalLink, Gauge, InfinityIcon, TerminalSquare, Wrench } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { AccountUsage, ScanSource, UsageBucket } from "@/lib/types";
import { PageHeader, MetricCard, SectionCard } from "@/components/product-ui";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/status-badge";
import { formatDateTime, SCAN_SOURCE_LABELS, TARGET_TYPE_LABELS } from "@/lib/presentation";

const BUCKETS: Record<UsageBucket, { label: string; description: string; icon: React.ReactNode }> = {
  dashboard: {
    label: "Dashboard scans",
    description: "Scans started from the authenticated web workspace.",
    icon: <Gauge className="size-5 text-brand-text" />,
  },
  cli: {
    label: "CLI scans",
    description: "Authenticated terminal scans counted by the CLI quota bucket.",
    icon: <TerminalSquare className="size-5 text-brand-text" />,
  },
  hook: {
    label: "Hook auto-scans",
    description: "Scans requested by the Claude Code pre-install workflow.",
    icon: <Activity className="size-5 text-brand-text" />,
  },
  auto_fix: {
    label: "Auto-fix PRs",
    description: "Fix It pull requests opened this period, Pro and Team only.",
    icon: <Wrench className="size-5 text-brand-text" />,
  },
};

export default function UsagePage() {
  const [usage, setUsage] = useState<AccountUsage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getUsage().then(setUsage).catch((err) => {
      setError(err instanceof ApiError ? err.message : "Could not load usage.");
    });
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Usage"
        description="Track each scan-credit bucket, its current limit, and the exact reset time for your account."
        actions={
          <Button render={<Link href="/pricing" />}>Compare plans</Button>
        }
      />

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load usage</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {!usage && !error ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-40 rounded-3xl" />)}
        </div>
      ) : null}

      {usage ? <UsageContent usage={usage} /> : null}
    </div>
  );
}

function UsageContent({ usage }: { usage: AccountUsage }) {
  const [sourceFilter, setSourceFilter] = useState<"all" | ScanSource>("all");
  const limited = usage.buckets.filter((bucket) => bucket.limit !== null);
  const totalUsed = usage.buckets.reduce((sum, bucket) => sum + bucket.used, 0);
  const nearestReset = limited.map((bucket) => bucket.resets_at).sort()[0] ?? null;
  const visibleActivity = sourceFilter === "all"
    ? usage.activity
    : usage.activity.filter((item) => item.source === sourceFilter);

  return (
    <>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <MetricCard label="Current plan" value={usage.tier} detail="Usage is measured separately for dashboard, CLI, and hook scans." tone={usage.tier === "free" ? "default" : "success"} />
        <MetricCard label="Scans used" value={totalUsed} detail="Combined activity across the three quota buckets in their current periods." />
        <MetricCard label="Next reset" value={nearestReset ? formatDateTime(nearestReset) : "Unlimited"} detail="Each bucket below retains its exact reset timestamp." tone="success" />
      </div>

      <SectionCard title="Scan-credit buckets" description="A scan credit is consumed only from the product surface that initiated the scan.">
        <div className="grid gap-4 xl:grid-cols-3">
          {usage.buckets
            .filter((bucket) => bucket.bucket !== "auto_fix" || bucket.limit !== 0)
            .map((bucket) => {
            const config = BUCKETS[bucket.bucket];
            const limit = bucket.limit;
            const unlimited = limit === null;
            const percent = limit === null ? 0 : Math.min(100, (bucket.used / limit) * 100);
            return (
              <article key={bucket.bucket} className="min-w-0 rounded-2xl border border-border bg-background/80 p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-2xl border border-brand/25 bg-brand/10">{config.icon}</div>
                  {unlimited ? <InfinityIcon className="size-5 text-brand-text" aria-label="Unlimited" /> : <span className="text-sm text-muted-foreground">{bucket.used} / {bucket.limit}</span>}
                </div>
                <h2 className="mt-4 text-base font-medium">{config.label}</h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{config.description}</p>
                {!unlimited ? <Progress value={percent} className="mt-4" /> : null}
                <div className="mt-4 flex items-start gap-2 text-xs leading-5 text-muted-foreground">
                  <CalendarClock className="mt-0.5 size-4 shrink-0" />
                  <span>{unlimited ? "No monthly limit" : `Resets ${formatDateTime(bucket.resets_at)}`}</span>
                </div>
              </article>
            );
          })}
        </div>
      </SectionCard>

      <SectionCard
        title="Usage activity"
        description="The latest 50 scans charged to your account, including the initiating surface and a direct link to its full report. Cached hook checks do not consume a credit and are not listed."
      >
        <div className="mb-5 flex flex-wrap gap-2" aria-label="Filter usage activity by source">
          {(["all", "dashboard", "cli", "hook"] as const).map((source) => (
            <Button
              key={source}
              type="button"
              size="sm"
              variant={sourceFilter === source ? "default" : "outline"}
              aria-pressed={sourceFilter === source}
              onClick={() => setSourceFilter(source)}
            >
              {source === "all" ? "All activity" : SCAN_SOURCE_LABELS[source]}
            </Button>
          ))}
        </div>

        {visibleActivity.length ? (
          <div className="divide-y divide-border overflow-hidden rounded-2xl border border-border">
            {visibleActivity.map((item) => (
              <article key={item.id} className="grid min-w-0 gap-3 bg-background/80 p-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:px-5">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{SCAN_SOURCE_LABELS[item.source]}</span>
                    <StatusBadge status={item.status} />
                    <span className="text-xs text-muted-foreground">{TARGET_TYPE_LABELS[item.target_type]}</span>
                  </div>
                  <p className="mt-2 truncate text-sm text-foreground" title={item.target}>{item.target}</p>
                  <p className="mt-1 text-xs text-muted-foreground">Used {formatDateTime(item.created_at)}</p>
                </div>
                <div className="flex items-center justify-between gap-4 sm:justify-end">
                  <div className="text-right">
                    <p className="text-xs text-muted-foreground">Score</p>
                    <p className="font-mono text-lg font-medium">{item.score ?? "—"}</p>
                  </div>
                  <Button variant="outline" size="sm" render={<Link href={`/scans/${item.id}`} aria-label={`Open report for ${item.target}`} />}>
                    Report <ExternalLink className="size-3.5" />
                  </Button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-border px-5 py-10 text-center">
            <p className="text-sm font-medium">No usage in this source yet</p>
            <p className="mt-2 text-sm text-muted-foreground">Run a scan from this surface and it will appear here with its report.</p>
          </div>
        )}
      </SectionCard>
    </>
  );
}
