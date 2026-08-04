"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { AccountUsage, Subscription } from "@/lib/types";
import { PageHeader, MetricCard, SectionCard } from "@/components/product-ui";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate, formatDateTime } from "@/lib/presentation";

const PLAN_COPY = {
  free: { price: "$0", billing: "No renewal", body: "Five CLI scans, two hook auto-scans, and five dashboard scans each month." },
  hobby: { price: "$9 / $7", billing: "One cycle at a time", body: "Monthly / effective annual monthly price, charged in USD with no automatic renewal." },
  pro: { price: "$34 / $29", billing: "One cycle at a time", body: "Monthly / effective annual monthly price, includes 15 auto-fix PRs/month, charged in USD with no automatic renewal." },
  team: { price: "$40 / $33 per seat", billing: "One cycle at a time", body: "Monthly / effective annual per-seat price, includes 15 auto-fix PRs/seat/month, charged in USD with no automatic renewal." },
} as const;

const BUCKET_LABEL: Record<string, string> = {
  hook: "Hook auto-scans",
  auto_fix: "Auto-fix PRs",
};

export default function BillingPage() {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [usage, setUsage] = useState<AccountUsage | null>(null);

  useEffect(() => {
    api
      .getSubscription()
      .then(setSubscription)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not load billing info."));
    api
      .getUsage()
      .then(setUsage)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not load usage info."));
  }, []);

  const plan = subscription ? PLAN_COPY[subscription.tier] : null;
  const expired = subscription?.tier !== "free" && subscription?.effective_tier === "free";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Billing"
        description="This product currently bills one cycle at a time. Nothing renews automatically, so your plan remains active until its paid-until date and then falls back when that period ends."
      />

      {subscription === null || usage === null ? (
        <div className="grid gap-4 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-40 rounded-3xl" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 xl:grid-cols-3">
          <MetricCard
            label="Current plan"
            value={subscription.effective_tier.charAt(0).toUpperCase() + subscription.effective_tier.slice(1)}
            detail={plan?.body}
            tone={subscription.effective_tier === "free" ? "default" : "success"}
          />
          <MetricCard
            label="Current pricing"
            value={plan?.price ?? "—"}
            detail={subscription.tier === "free" ? "Free plan" : "Monthly / annual options from pricing"}
          />
          <MetricCard
            label="Renewal behavior"
            value={plan?.billing ?? "—"}
            detail={
              subscription.paid_until
                ? expired
                  ? `Expired on ${formatDate(subscription.paid_until)}`
                  : `Active through ${formatDate(subscription.paid_until)}`
                : "Upgrade from free whenever you need higher limits."
            }
          />
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_360px]">
        <SectionCard
          title="Plan details"
          description="Only functional product behavior is described here."
          action={
            <Button render={<Link href="/pricing" />}>{expired ? "Renew or change plan" : "View pricing"}</Button>
          }
        >
          {subscription ? (
            <div className="space-y-4 text-sm leading-6 text-muted-foreground">
              <p>
                Your stored plan is <strong className="text-foreground">{subscription.tier}</strong>. The currently effective tier is{" "}
                <strong className="text-foreground">{subscription.effective_tier}</strong>.
              </p>
              <p>
                {subscription.paid_until
                  ? expired
                    ? `That paid period ended on ${formatDate(subscription.paid_until)}. Higher limits will not return until you pay for another cycle.`
                    : `The current paid period ends on ${formatDate(subscription.paid_until)}. The system does not charge automatically after that date.`
                  : "Free plans have no payment date and no invoice history in the current backend."}
              </p>
              <p>
                Invoice history, repayment flows, and seat management are not exposed by the current backend, so they are not shown here.
              </p>
            </div>
          ) : null}
        </SectionCard>

        <SectionCard title="Usage this period" description="Limits come from the current account and tier configuration.">
          {usage ? (
            <div className="space-y-4">
              {usage.buckets
                .filter((bucket) => bucket.bucket !== "auto_fix" || bucket.limit !== 0)
                .map((bucket) => (
                  <div key={bucket.bucket} className="rounded-2xl border border-border bg-background/80 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-medium text-foreground capitalize">
                        {BUCKET_LABEL[bucket.bucket] ?? `${bucket.bucket} scans`}
                      </span>
                      <span className="text-sm text-muted-foreground">
                        {bucket.limit === null ? "Unlimited" : `${bucket.used} / ${bucket.limit}`}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-muted-foreground">
                      Resets {formatDateTime(bucket.resets_at)}
                    </p>
                  </div>
                ))}
            </div>
          ) : null}
        </SectionCard>
      </div>

      {subscription && (subscription.effective_tier === "pro" || subscription.effective_tier === "team") ? (
        <AutofixSection />
      ) : null}
    </div>
  );
}

function AutofixSection() {
  const [status, setStatus] = useState<{ connected: boolean; account_login: string | null } | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [buyingAddon, setBuyingAddon] = useState(false);

  useEffect(() => {
    api
      .getGithubStatus()
      .then(setStatus)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not load GitHub connection status."));
  }, []);

  async function connectGithub() {
    setConnecting(true);
    try {
      const { url } = await api.getGithubInstallUrl();
      window.location.href = url;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not start GitHub connection.");
      setConnecting(false);
    }
  }

  async function buyAddon() {
    setBuyingAddon(true);
    try {
      const { order_id, amount_paise, currency, razorpay_key_id } = await api.createAutofixAddonCheckout();
      const script = document.createElement("script");
      script.src = "https://checkout.razorpay.com/v1/checkout.js";
      await new Promise<void>((resolve, reject) => {
        script.onload = () => resolve();
        script.onerror = () => reject(new Error("Could not load Razorpay checkout."));
        document.body.appendChild(script);
      });
      type RazorpaySuccess = { razorpay_payment_id: string; razorpay_order_id: string; razorpay_signature: string };
      type RazorpayInstance = { open: () => void; on: (event: string, handler: (resp: unknown) => void) => void };
      const Razorpay = (window as unknown as { Razorpay: new (opts: object) => RazorpayInstance }).Razorpay;
      const checkout = new Razorpay({
        key: razorpay_key_id,
        order_id,
        amount: amount_paise,
        currency,
        name: "Aevrin",
        description: "+10 auto-fix PRs",
        theme: { color: "#000000" },
        handler: async (resp: unknown) => {
          const { razorpay_payment_id, razorpay_order_id, razorpay_signature } = resp as RazorpaySuccess;
          try {
            await api.verifyPayment(razorpay_order_id, razorpay_payment_id, razorpay_signature);
            toast.success("+10 auto-fix PRs added to this billing period.");
          } catch (err) {
            toast.error(err instanceof ApiError ? err.message : "Payment succeeded but activation failed — contact support.");
          }
        },
      });
      checkout.on("payment.failed", () => toast.error("Payment failed. You weren't charged — try again."));
      checkout.open();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not start checkout.");
    } finally {
      setBuyingAddon(false);
    }
  }

  return (
    <SectionCard
      title="Auto-fix (Fix It)"
      description="Connecting GitHub grants Aevrin access only to repositories you explicitly select during installation, scoped and revocable entirely through GitHub's own settings."
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-sm text-muted-foreground">
          {status === null ? (
            "Checking connection status…"
          ) : status.connected ? (
            <span>
              Connected as <strong className="text-foreground">{status.account_login}</strong>. Fix It can open draft
              PRs on repositories you granted access to.
            </span>
          ) : (
            "Not connected yet — Fix It will prompt for this the first time you use it on a repository, or connect now."
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          {!status?.connected && (
            <Button variant="outline" disabled={connecting} onClick={() => void connectGithub()}>
              {connecting ? "Redirecting…" : "Connect GitHub"}
            </Button>
          )}
          <Button variant="outline" disabled={buyingAddon} onClick={() => void buyAddon()}>
            {buyingAddon ? "Please wait…" : "Buy +10 PRs ($4)"}
          </Button>
        </div>
      </div>
    </SectionCard>
  );
}
