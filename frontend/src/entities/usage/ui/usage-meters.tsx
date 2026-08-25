"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usageApi } from "@/entities/usage";
import type { AccountUsage } from "@/entities/usage";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { buttonVariants } from "@/shared/ui/button";
import { UPGRADE_THRESHOLD, USAGE_BUCKETS, usageFillColor } from "@/entities/usage";

function daysUntil(iso: string): number {
  const ms = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(ms / (1000 * 60 * 60 * 24)));
}

export function UsageMeters() {
  const [usage, setUsage] = useState<AccountUsage | null>(null);

  useEffect(() => {
    usageApi.getUsage().then(setUsage).catch(() => setUsage(null));
  }, []);

  if (!usage) return null;

  const nearLimit = usage.buckets.some((b) => b.limit !== null && b.used / b.limit >= UPGRADE_THRESHOLD);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          Usage this period
          <span className="rounded-full border border-brand/30 bg-brand/10 px-2 py-0.5 text-[11px] font-medium text-brand-text capitalize">
            {usage.tier}
          </span>
        </CardTitle>
        {(nearLimit || usage.tier === "free") && (
          <Link href="/pricing" className={buttonVariants({ size: "sm", variant: "outline" })}>
            Upgrade
          </Link>
        )}
      </CardHeader>
      {/* Container queries, not viewport breakpoints: this card renders both
          full-width and inside a ~360px dashboard sidebar column. A `lg:`
          viewport rule fired in the narrow column too and crushed the labels
          into "CLI s… Hook … Dash…". @container measures the actual box, so
          the grid only widens when there's genuinely room. */}
      <CardContent className="@container flex flex-1 flex-col">
        <div className="grid gap-4 @md:grid-cols-2 @3xl:grid-cols-4">
          {usage.buckets
            .map((bucket, index) => {
              const meta = USAGE_BUCKETS[bucket.bucket];
              const Icon = meta.icon;
              const unlimited = bucket.limit === null;
              const ratio = unlimited ? 0 : bucket.used / bucket.limit!;
              const pct = unlimited ? 0 : Math.min(100, ratio * 100);

              const fill = usageFillColor(bucket.bucket, ratio);

              return (
                <div key={bucket.bucket} className="flex flex-col gap-1.5">
                  {/* gap-3 + shrink-0 on the count: without them the label and
                      value collide at narrow column widths ("Dashboard0 / 5"). */}
                  <div className="flex items-baseline justify-between gap-3 text-sm">
                    <span className="flex min-w-0 items-center gap-1.5">
                      <Icon aria-hidden="true" className="size-3.5 shrink-0" style={{ color: meta.color }} />
                      <span className="truncate">{meta.label}</span>
                    </span>
                    <span className="shrink-0 tabular-nums text-muted-foreground">
                      <span className="font-medium text-foreground">{bucket.used}</span>
                      {unlimited ? "" : ` / ${bucket.limit}`}
                    </span>
                  </div>

                  {unlimited ? null : (
                    <div
                      role="progressbar"
                      aria-valuenow={Math.round(pct)}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`${meta.label} used`}
                      className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
                    >
                      <div
                        className="bar-grow-x h-full rounded-full"
                        style={
                          { width: `${pct}%`, background: fill, "--i": index } as React.CSSProperties
                        }
                      />
                    </div>
                  )}

                  <span className="text-xs text-muted-foreground">
                    {unlimited
                      ? "Usage-based"
                      : ratio >= 1
                        ? "Limit reached"
                        : `Resets in ${daysUntil(bucket.resets_at)}d`}
                  </span>
                </div>
              );
            })}
        </div>

        {/* Pinned to the bottom so the card fills its grid row instead of
            leaving a block of empty surface beside the findings list. */}
        <Link
          href="/usage"
          className="mt-auto flex items-center justify-between gap-3 border-t border-border pt-3 text-[12px] text-muted-foreground transition-colors hover:text-foreground"
        >
          Per-scan usage history
          <span aria-hidden="true">→</span>
        </Link>
      </CardContent>
    </Card>
  );
}
