"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { Subscription } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

// Razorpay has no hosted customer-portal equivalent to Stripe's — this page
// exists specifically to back that gap: current plan/status, next charge
// (implied by subscription_status), and cancel, all against apps/api's
// /billing/* endpoints.
export default function BillingPage() {
  const [sub, setSub] = useState<Subscription | null>(null);
  const [canceling, setCanceling] = useState(false);

  function refresh() {
    api
      .getSubscription()
      .then(setSub)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not load billing info."));
  }

  useEffect(refresh, []);

  async function cancel() {
    setCanceling(true);
    try {
      await api.cancelSubscription();
      toast.success("Subscription canceled — you'll keep access until the end of this billing period.");
      refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not cancel subscription.");
    } finally {
      setCanceling(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="text-2xl font-semibold tracking-tight">Billing</h1>
      <p className="mt-1 text-sm text-muted-foreground">Manage your Aevrin subscription.</p>

      {sub === null && <Skeleton className="mt-6 h-32 w-full" />}

      {sub && (
        <Card className="mt-6">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-medium capitalize">{sub.tier} plan</CardTitle>
              {sub.subscription_status && (
                <Badge variant={sub.subscription_status === "active" ? "secondary" : "outline"}>
                  {sub.subscription_status}
                </Badge>
              )}
            </div>
            {sub.downgrade_effective_at && (
              <CardDescription>
                Your plan changed on {new Date(sub.downgrade_effective_at).toLocaleDateString()} — existing scan
                history is kept through a grace period, not deleted immediately.
              </CardDescription>
            )}
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {sub.tier === "free" ? (
              <Link href="/pricing" className={buttonVariants()}>
                Upgrade
              </Link>
            ) : sub.subscription_status === "active" ? (
              <Button variant="outline" onClick={cancel} disabled={canceling}>
                {canceling ? "Canceling…" : "Cancel subscription"}
              </Button>
            ) : (
              <Link href="/pricing" className={buttonVariants()}>
                Resubscribe
              </Link>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
