"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CreditCard, Receipt } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { AccountUsage, Payment, Subscription } from "@/lib/types";
import { PageHeader, MetricCard, SectionCard } from "@/components/product-ui";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate, formatDateTime } from "@/lib/presentation";

const PAYMENT_TIER_LABEL: Record<Payment["tier"], string> = {
  hobby: "Hobby",
  pro: "Pro",
  team: "Team",
  autofix_addon: "+10 auto-fix PRs",
};

const PAYMENT_STATUS_STYLE: Record<Payment["status"], string> = {
  paid: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  created: "border-border text-muted-foreground",
  failed: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400",
};

const PAYMENT_STATUS_LABEL: Record<Payment["status"], string> = {
  paid: "Paid",
  created: "Not completed",
  failed: "Failed",
};

function formatMoney(amountPaise: number, currency: string) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 2 }).format(
    amountPaise / 100,
  );
}

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
  const [payments, setPayments] = useState<Payment[] | null>(null);

  useEffect(() => {
    api
      .getSubscription()
      .then(setSubscription)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not load billing info."));
    api
      .getUsage()
      .then(setUsage)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not load usage info."));
    api
      .getPayments()
      .then(setPayments)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not load billing history."));
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
              <div className="flex items-start gap-3 rounded-2xl border border-border/80 bg-background/70 p-4">
                <CreditCard className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <div>
                  <p className="font-medium text-foreground">Payment method</p>
                  <p className="mt-1">
                    Aevrin doesn&apos;t store a card. Each cycle is a one-time Razorpay Standard Checkout — you pick
                    the card or method on Razorpay&apos;s own checkout screen every time you pay, and nothing is
                    charged automatically in between.
                  </p>
                </div>
              </div>
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

      <SectionCard
        title="Billing history"
        description="Every checkout this account has started, most recent first — including ones that didn't complete, so a missing charge is never a mystery."
      >
        {payments === null ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-14 rounded-2xl" />
            ))}
          </div>
        ) : payments.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border px-5 py-10 text-center">
            <Receipt className="size-6 text-muted-foreground" />
            <p className="text-sm font-medium">No payments yet</p>
            <p className="max-w-sm text-sm text-muted-foreground">
              Nothing has been charged on this account. Free needs no payment method at all.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto" tabIndex={0} aria-label="Billing history">
            <table className="w-full min-w-[560px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-[0.08em] text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Date</th>
                  <th className="py-2 pr-4 font-medium">Plan</th>
                  <th className="py-2 pr-4 font-medium">Cycle</th>
                  <th className="py-2 pr-4 font-medium">Amount</th>
                  <th className="py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((payment) => (
                  <tr key={payment.id} className="border-b border-border/50 last:border-0">
                    <td className="py-3 pr-4 text-muted-foreground">{formatDate(payment.created_at)}</td>
                    <td className="py-3 pr-4">
                      {PAYMENT_TIER_LABEL[payment.tier]}
                      {payment.seats > 1 ? ` · ${payment.seats} seats` : ""}
                      {payment.byok ? " · BYOK" : ""}
                    </td>
                    <td className="py-3 pr-4 capitalize text-muted-foreground">{payment.cycle}</td>
                    <td className="py-3 pr-4 font-medium">{formatMoney(payment.amount_paise, payment.currency)}</td>
                    <td className="py-3">
                      <Badge variant="outline" className={PAYMENT_STATUS_STYLE[payment.status]}>
                        {PAYMENT_STATUS_LABEL[payment.status]}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {subscription && (subscription.effective_tier === "pro" || subscription.effective_tier === "team") ? (
        <AutofixSection />
      ) : null}

      <SectionCard title="Need something else?" description="Refunds, receipts for accounting, or anything billing-related.">
        <p className="text-sm leading-6 text-muted-foreground">
          Reach the same team that handles product support — no separate billing queue or phone tree.{" "}
          <a href="mailto:support@aevrin.net" className="font-medium text-foreground underline underline-offset-2">
            support@aevrin.net
          </a>
          .
        </p>
      </SectionCard>
    </div>
  );
}

const GITHUB_CALLBACK_MESSAGE: Record<string, { message: string; ok: boolean }> = {
  connected: { message: "GitHub connected — Fix It can now open pull requests on the repos you granted.", ok: true },
  cancelled: { message: "GitHub connection cancelled — nothing was granted.", ok: false },
  invalid_state: { message: "That connection link expired — try connecting again.", ok: false },
  error: { message: "Could not complete the GitHub connection — try again.", ok: false },
};

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

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get("github");
    if (!result) return;
    const outcome = GITHUB_CALLBACK_MESSAGE[result];
    if (outcome) {
      if (outcome.ok) {
        toast.success(outcome.message);
      } else {
        toast.error(outcome.message);
      }
    }
    params.delete("github");
    const query = params.toString();
    window.history.replaceState({}, "", query ? `?${query}` : window.location.pathname);
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
