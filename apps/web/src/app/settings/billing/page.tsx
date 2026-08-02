"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { Subscription } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

// Billing is one-time-payment-per-cycle, not auto-recurring (see
// apps/api's routers/billing.py) — there's no subscription to cancel, just
// a paid-until date. This page shows that date and a link back to pricing
// to renew or upgrade, backed by GET /billing/subscription.
export default function BillingPage() {
  const [sub, setSub] = useState<Subscription | null>(null);

  useEffect(() => {
    api
      .getSubscription()
      .then(setSub)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not load billing info."));
  }, []);

  const expired = sub?.tier !== "free" && sub?.effective_tier === "free";

  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="text-2xl font-semibold tracking-tight">Billing</h1>
      <p className="mt-1 text-sm text-muted-foreground">Your Aevrin plan is billed one cycle at a time — no auto-renewal.</p>

      {sub === null && <Skeleton className="mt-6 h-32 w-full" />}

      {sub && (
        <Card className="mt-6">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-medium capitalize">{sub.effective_tier} plan</CardTitle>
              {expired && <Badge variant="outline">Expired</Badge>}
            </div>
            {sub.paid_until && (
              <CardDescription>
                {expired
                  ? `Your ${sub.tier} plan's paid period ended on ${new Date(sub.paid_until).toLocaleDateString()}. Renew to restore your limits.`
                  : `Paid through ${new Date(sub.paid_until).toLocaleDateString()}. You'll be prompted to pay again after that — nothing charges automatically.`}
              </CardDescription>
            )}
          </CardHeader>
          <CardContent>
            {(sub.effective_tier === "free" || expired) && (
              <Link href="/pricing" className={buttonVariants()}>
                {expired ? "Renew" : "Upgrade"}
              </Link>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
