"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CalendarClock, ExternalLink, InfinityIcon } from "lucide-react";
import { ApiError } from "@/shared/api";
import { usageApi } from "@/entities/usage";
import type { ScanSource } from "@/entities/scan";
import type { AccountUsage } from "@/entities/usage";
import { PageHeader, MetricCard, SectionCard } from "@/shared/ui";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { StatusBadge } from "@/entities/scan";
import { USAGE_BUCKETS, usageFillColor } from "@/entities/usage";
import { Usage3DChart } from "@/entities/usage/ui/usage-3d-chart";
import { SCAN_SOURCE_LABELS, TARGET_TYPE_LABELS } from "@/entities/scan";
import { formatDate, formatDateTime } from "@/shared/lib/format";

export function UsagePage() {
  const [usage, setUsage] = useState<AccountUsage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    usageApi.getUsage().then(setUsage).catch((err) => {
      setError(err instanceof ApiError ? err.message : "Could not load usage.");
    });
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        pretitle="Account"
        title="Usage"
        description="Track each scan-credit bucket, its current limit, and the exact reset time for your account."
        actions={
          <Button nativeButton={false} render={<Link href="/pricing" />}>Compare plans</Button>
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
          {Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-40 rounded-xl" />)}
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
      {/* Period summary + the 3D consumption chart in one band. The chart
          answers "how much of each bucket have I burned", depth separates
          spent from headroom far better than two shades of a flat bar. */}
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <SectionCard
          title="Consumption this period"
          description="Solid blocks are credits spent. The outlined block above each is the headroom left before that bucket pauses."
        >
          <Usage3DChart
            bars={usage.buckets
              .filter((bucket) => bucket.bucket !== "auto_fix" || bucket.limit !== 0)
              .map((bucket) => ({ bucket: bucket.bucket, used: bucket.used, limit: bucket.limit }))}
          />
        </SectionCard>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
          <MetricCard
            label="Current plan"
            value={usage.tier.charAt(0).toUpperCase() + usage.tier.slice(1)}
            detail="Usage is measured separately for dashboard, CLI, and hook scans."
            tone={usage.tier === "free" ? "default" : "success"}
          />
          <MetricCard
            label="Scans used"
            value={totalUsed}
            detail="Combined activity across every quota bucket in its current period."
          />
          <MetricCard
            label="Next reset"
            value={nearestReset ? formatDate(nearestReset) : "No limit"}
            detail="Each bucket below retains its exact reset timestamp."
          />
        </div>
      </div>

      <SectionCard title="Scan-credit buckets" description="A scan credit is consumed only from the product surface that initiated the scan.">
        <div className="grid gap-4 xl:grid-cols-3">
          {usage.buckets
            .filter((bucket) => bucket.bucket !== "auto_fix" || bucket.limit !== 0)
            .map((bucket, index) => {
              const config = USAGE_BUCKETS[bucket.bucket];
              const Icon = config.icon;
              const limit = bucket.limit;
              const unlimited = limit === null;
              const ratio = unlimited ? 0 : bucket.used / limit;
              const percent = unlimited ? 0 : Math.min(100, ratio * 100);
              const fill = usageFillColor(bucket.bucket, ratio);

              return (
                <article
                  key={bucket.bucket}
                  className="panel-rise-item min-w-0 rounded-xl border border-border bg-background/80 p-5 transition-colors hover:border-border/60"
                  style={{ "--i": index } as React.CSSProperties}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div
                      className="flex size-10 shrink-0 items-center justify-center rounded-xl border"
                      style={{
                        borderColor: `color-mix(in oklab, ${config.color} 30%, transparent)`,
                        background: `color-mix(in oklab, ${config.color} 12%, transparent)`,
                      }}
                    >
                      <Icon className="size-5" style={{ color: config.color }} />
                    </div>
                    {unlimited ? (
                      <InfinityIcon className="size-5 text-muted-foreground" aria-label="No monthly limit" />
                    ) : (
                      <span className="text-sm tabular-nums text-muted-foreground">
                        <span className="text-base font-medium text-foreground">{bucket.used}</span> / {bucket.limit}
                      </span>
                    )}
                  </div>
                  <h2 className="mt-4 text-base font-medium">{config.label}</h2>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">{config.description}</p>
                  {unlimited ? null : (
                    <div
                      role="progressbar"
                      aria-valuenow={Math.round(percent)}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`${config.label} used`}
                      className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-muted"
                    >
                      <div
                        className="bar-grow-x h-full rounded-full"
                        style={{ width: `${percent}%`, background: fill, "--i": index } as React.CSSProperties}
                      />
                    </div>
                  )}
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
          <div className="divide-y divide-border overflow-hidden rounded-xl border border-border">
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
                    <p className="font-mono text-lg font-medium">{item.score ?? "-"}</p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    nativeButton={false}
                    render={<Link href={`/scans/${item.id}`} aria-label={`Open report for ${item.target}`} />}
                  >
                    Report <ExternalLink className="size-3.5" />
                  </Button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border px-5 py-10 text-center">
            <p className="text-sm font-medium">No usage in this source yet</p>
            <p className="mt-2 text-sm text-muted-foreground">Run a scan from this surface and it will appear here with its report.</p>
          </div>
        )}
      </SectionCard>
    </>
  );
}
