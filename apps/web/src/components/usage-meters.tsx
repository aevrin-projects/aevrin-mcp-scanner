"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { AccountUsage, UsageBucket } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { buttonVariants } from "@/components/ui/button";

const BUCKET_LABELS: Record<UsageBucket, string> = {
  cli: "CLI scans",
  hook: "Hook auto-scans",
  dashboard: "Dashboard scans",
  auto_fix: "Auto-fix PRs",
};

// The single most important retention surface in the product (addendum
// §6) — an upgrade CTA appears once any meter crosses ~80%.
const UPGRADE_THRESHOLD = 0.8;

function daysUntil(iso: string): number {
  const ms = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(ms / (1000 * 60 * 60 * 24)));
}

export function UsageMeters() {
  const [usage, setUsage] = useState<AccountUsage | null>(null);

  useEffect(() => {
    api.getUsage().then(setUsage).catch(() => setUsage(null));
  }, []);

  if (!usage) return null;

  const nearLimit = usage.buckets.some((b) => b.limit !== null && b.used / b.limit >= UPGRADE_THRESHOLD);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          Usage this period · {usage.tier} plan
        </CardTitle>
        {(nearLimit || usage.tier === "free") && (
          <Link href="/pricing" className={buttonVariants({ size: "sm", variant: "outline" })}>
            Upgrade
          </Link>
        )}
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {usage.buckets
          .filter((bucket) => bucket.bucket !== "auto_fix" || bucket.limit !== 0)
          .map((bucket) => {
          const unlimited = bucket.limit === null;
          const pct = unlimited ? 0 : Math.min(100, (bucket.used / bucket.limit!) * 100);
          return (
            <div key={bucket.bucket} className="flex flex-col gap-1.5">
              <div className="flex items-baseline justify-between text-sm">
                <span>{BUCKET_LABELS[bucket.bucket]}</span>
                <span className="text-muted-foreground">
                  {bucket.used}
                  {unlimited ? "" : ` / ${bucket.limit}`}
                </span>
              </div>
              {!unlimited && <Progress value={pct} />}
              <span className="text-xs text-muted-foreground">
                {unlimited ? "Unlimited" : `Resets in ${daysUntil(bucket.resets_at)}d`}
              </span>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
