"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, CreditCard, GitPullRequest, KeyRound, Receipt, Wrench, Zap } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { AccountUsage, Payment, Subscription } from "@/lib/types";
import { PageHeader, SectionCard } from "@/components/product-ui";
import { USAGE_BUCKETS, usageFillColor } from "@/components/usage-bucket-meta";
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

// Full labels for every bucket — a `capitalize` utility was previously doing
// the work and rendered "cli scans" as "Cli Scans".

export default function BillingPage() {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [usage, setUsage] = useState<AccountUsage | null>(null);
  const [payments, setPayments] = useState<Payment[] | null>(null);
  // Captured once on mount: reading the clock during render is impure and
  // would make the period bar jitter on every re-render.
  const [now] = useState(() => Date.now());

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

  // Earliest bucket reset — the only period a Free account actually has.
  const nextReset =
    usage?.buckets
      .map((bucket) => bucket.resets_at)
      .filter(Boolean)
      .sort()[0] ?? null;

  // How far through the current period we are. Both branches assume a 30-day
  // window because neither the subscription nor the usage payload carries a
  // period *start*; the bar is a rough sense of "how much runway is left", and
  // the exact end date is always printed next to it.
  const cycleProgress = (() => {
    const end = subscription?.paid_until ?? nextReset;
    if (!end) return 0;
    if (expired) return 100;
    const remainingMs = new Date(end).getTime() - now;
    const windowMs = 30 * 24 * 60 * 60 * 1000;
    return Math.min(100, Math.max(0, ((windowMs - remainingMs) / windowMs) * 100));
  })();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Billing"
        description="This product currently bills one cycle at a time. Nothing renews automatically, so your plan remains active until its paid-until date and then falls back when that period ends."
      />

      {subscription === null || usage === null ? (
        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.25fr)_360px]">
          <Skeleton className="h-72 rounded-xl" />
          <Skeleton className="h-72 rounded-xl" />
        </div>
      ) : (
        /* The plan is this page's headline, so it gets one large card instead
           of three equal metric tiles. On the old layout "Free", "$0" and
           "No renewal" carried identical weight and told a buyer nothing
           about what to do next. */
        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.25fr)_360px]">
          <section className="relative overflow-hidden rounded-xl border border-border bg-card">
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-0 top-0 h-48"
              style={{
                background:
                  "radial-gradient(110% 100% at 0% 0%, color-mix(in oklab, var(--brand) 15%, transparent), transparent 68%)",
              }}
            />
            <div className="relative p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-[11px] font-medium tracking-[0.12em] text-muted-foreground uppercase">
                    Current plan
                  </p>
                  <div className="mt-2.5 flex flex-wrap items-baseline gap-3">
                    <h2 className="text-3xl font-semibold tracking-tight">
                      {subscription.effective_tier.charAt(0).toUpperCase() + subscription.effective_tier.slice(1)}
                    </h2>
                    <span className="text-lg text-muted-foreground">{plan?.price}</span>
                    {expired ? (
                      <Badge variant="outline" className="border-severity-high/40 bg-severity-high/10 text-severity-high">
                        Period ended
                      </Badge>
                    ) : subscription.effective_tier !== "free" ? (
                      <Badge variant="outline" className="border-chart-1/40 bg-chart-1/10 text-chart-1">
                        Active
                      </Badge>
                    ) : null}
                  </div>
                  <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted-foreground">{plan?.body}</p>
                </div>

                <Button nativeButton={false} render={<Link href="/pricing" />} className="shrink-0">
                  {expired ? "Renew plan" : subscription.effective_tier === "free" ? "Upgrade" : "Change plan"}
                </Button>
              </div>

              {/* Period bar. Free has no paid cycle, so it shows the quota
                  reset rather than inventing a billing period. */}
              <div className="mt-6 border-t border-border pt-5">
                <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
                  <span className="text-muted-foreground">
                    {subscription.paid_until ? (expired ? "Paid period ended" : "Paid period ends") : "Quota resets"}
                  </span>
                  <span className="font-medium tabular-nums">
                    {subscription.paid_until
                      ? formatDate(subscription.paid_until)
                      : nextReset
                        ? formatDate(nextReset)
                        : "—"}
                  </span>
                </div>
                <div
                  role="progressbar"
                  aria-valuenow={Math.round(cycleProgress)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label="Current period elapsed"
                  className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-muted"
                >
                  <div
                    className="bar-grow-x h-full rounded-full"
                    style={{
                      width: `${cycleProgress}%`,
                      background: expired ? "var(--severity-high)" : "var(--brand)",
                    }}
                  />
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {expired
                    ? "Higher limits will not return until you pay for another cycle."
                    : "Nothing is charged automatically — each cycle is an explicit checkout."}
                </p>
              </div>

              <dl className="mt-6 grid gap-4 border-t border-border pt-5 sm:grid-cols-3">
                <div>
                  <dt className="text-xs text-muted-foreground">Renewal</dt>
                  <dd className="mt-1 text-sm font-medium">{plan?.billing ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Stored plan</dt>
                  <dd className="mt-1 text-sm font-medium capitalize">{subscription.tier}</dd>
                </div>
                <div>
                  <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <CreditCard className="size-3.5" />
                    Payment method
                  </dt>
                  <dd className="mt-1 text-sm font-medium">None stored</dd>
                </div>
              </dl>

              <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
                Aevrin doesn&apos;t store a card. Each cycle is a one-time Razorpay Standard Checkout — you pick the
                card or method on Razorpay&apos;s own screen every time you pay, and nothing is charged in between.
              </p>
            </div>
          </section>

          <SectionCard title="Usage this period" description="Limits come from the current account and tier configuration.">
            {/* Same hues as the dashboard meters and /usage, so a bucket keeps
                one identity across the product. The bar turns amber near the
                limit and red at it — on a billing page that is the whole point
                of the section, so it should be impossible to miss. */}
            <div className="space-y-3">
              {usage.buckets
                .filter((bucket) => bucket.bucket !== "auto_fix" || bucket.limit !== 0)
                .map((bucket, index) => {
                  const meta = USAGE_BUCKETS[bucket.bucket];
                  const Icon = meta.icon;
                  const unlimited = bucket.limit === null;
                  const ratio = unlimited ? 0 : bucket.used / bucket.limit!;
                  const percent = unlimited ? 0 : Math.min(100, ratio * 100);

                  return (
                    <div key={bucket.bucket} className="rounded-xl border border-border bg-background/80 p-4">
                      <div className="flex items-center justify-between gap-3">
                        <span className="flex min-w-0 items-center gap-2 text-sm font-medium text-foreground">
                          <Icon aria-hidden="true" className="size-4 shrink-0" style={{ color: meta.color }} />
                          <span className="truncate">{meta.label}</span>
                        </span>
                        <span className="shrink-0 text-sm tabular-nums text-muted-foreground">
                          {unlimited ? (
                            "Usage-based"
                          ) : (
                            <>
                              <span className="font-medium text-foreground">{bucket.used}</span> / {bucket.limit}
                            </>
                          )}
                        </span>
                      </div>
                      {unlimited ? null : (
                        <div
                          role="progressbar"
                          aria-valuenow={Math.round(percent)}
                          aria-valuemin={0}
                          aria-valuemax={100}
                          aria-label={`${meta.label} used`}
                          className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted"
                        >
                          <div
                            className="bar-grow-x h-full rounded-full"
                            style={
                              {
                                width: `${percent}%`,
                                background: usageFillColor(bucket.bucket, ratio),
                                "--i": index,
                              } as React.CSSProperties
                            }
                          />
                        </div>
                      )}
                      <p className="mt-2.5 text-xs leading-5 text-muted-foreground">
                        Resets {formatDateTime(bucket.resets_at)}
                      </p>
                    </div>
                  );
                })}
            </div>
          </SectionCard>
        </div>
      )}

      {/* Add-ons sit above billing history, not at the page bottom: buying one
          is the main reason anyone opens this page, and a purchase path that
          requires scrolling past invoices is effectively invisible. Shown to
          every tier — hiding them from Free meant nobody could discover they
          exist. */}
      {subscription ? <AutofixSection tier={subscription.effective_tier} /> : null}

      <SectionCard
        title="Billing history"
        description="Every checkout this account has started, most recent first — including ones that didn't complete, so a missing charge is never a mystery."
      >
        {payments === null ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-14 rounded-xl" />
            ))}
          </div>
        ) : payments.length === 0 ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border px-5 py-10 text-center">
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

// Each of these is a genuinely different outcome. They were previously all
// reported as "cancelled", which told someone who had just granted access
// that they hadn't — the exact confusion behind "I approved it and nothing
// updated".
const GITHUB_CALLBACK_MESSAGE: Record<string, { message: string; ok: boolean }> = {
  connected: { message: "GitHub connected — Fix It can now open pull requests on the repos you granted.", ok: true },
  cancelled: { message: "GitHub connection cancelled — nothing was granted.", ok: false },
  invalid_state: { message: "That connection link expired — try connecting again.", ok: false },
  authorized_not_installed: {
    message:
      "You authorized Aevrin but didn't finish installing it, so it has no repository access yet. Use Connect GitHub and pick the repositories on the install screen.",
    ok: false,
  },
  needs_relink: {
    message:
      "Installed on GitHub, but it arrived without the link that ties it to this Aevrin account. Click Connect GitHub here to finish — it won't ask for access again.",
    ok: false,
  },
  approval_pending: {
    message: "Requested — an owner of that GitHub organization has to approve the install before it takes effect.",
    ok: false,
  },
  error: { message: "Could not complete the GitHub connection — try again.", ok: false },
};

/**
 * One add-on, presented as something you buy: an icon in its own tinted
 * chip, the price as the largest thing in the card, what you actually get as
 * a short list, and a full-width CTA pinned to the bottom so every card's
 * button lines up. The previous version was a text row with the price as a
 * gray chip — it read as documentation, not as a product.
 *
 * `state` is honest about availability: an add-on that can't be bought yet
 * renders a disabled CTA and says why, rather than a live-looking button
 * that does nothing.
 */
function AddOnCard({
  title,
  price,
  unit,
  body,
  bullets,
  accent,
  Icon,
  state,
  action,
  index,
}: {
  title: string;
  price: string;
  unit?: string;
  body: string;
  bullets: string[];
  accent: string;
  Icon: typeof Wrench;
  state?: { label: string; tone: "ok" | "muted" };
  action: React.ReactNode;
  index: number;
}) {
  return (
    <article
      className="panel-rise-item group/addon relative flex flex-col overflow-hidden rounded-xl border border-border bg-background/80 transition-colors hover:border-brand/30"
      style={{ "--i": index } as React.CSSProperties}
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-28 opacity-60 transition-opacity duration-500 group-hover/addon:opacity-100"
        style={{ background: `radial-gradient(95% 100% at 20% 0%, color-mix(in oklab, ${accent} 13%, transparent), transparent 70%)` }}
      />

      <div className="relative flex flex-1 flex-col p-5">
        <div className="flex items-start justify-between gap-3">
          <span
            className="flex size-10 shrink-0 items-center justify-center rounded-xl border"
            style={{
              borderColor: `color-mix(in oklab, ${accent} 32%, transparent)`,
              background: `color-mix(in oklab, ${accent} 12%, transparent)`,
            }}
          >
            <Icon className="size-5" style={{ color: accent }} />
          </span>
          {state ? (
            <span
              className={
                state.tone === "ok"
                  ? "rounded-full border border-chart-1/40 bg-chart-1/10 px-2 py-0.5 text-[11px] font-medium text-chart-1"
                  : "rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground"
              }
            >
              {state.label}
            </span>
          ) : null}
        </div>

        <h3 className="mt-4 text-[15px] font-medium text-foreground">{title}</h3>

        <p className="mt-2 flex items-baseline gap-1.5">
          <span className="text-2xl font-semibold tracking-tight tabular-nums">{price}</span>
          {unit ? <span className="text-[12px] text-muted-foreground">{unit}</span> : null}
        </p>

        <p className="mt-2.5 text-[13px] leading-relaxed text-muted-foreground">{body}</p>

        <ul className="mt-4 space-y-1.5">
          {bullets.map((bullet) => (
            <li key={bullet} className="flex items-start gap-2 text-[12.5px] text-muted-foreground">
              <Check className="mt-0.5 size-3.5 shrink-0" style={{ color: accent }} />
              {bullet}
            </li>
          ))}
        </ul>

        <div className="mt-5 flex-1" />
        <div className="[&>*]:w-full">{action}</div>
      </div>
    </article>
  );
}

function AutofixSection({ tier }: { tier: Subscription["effective_tier"] }) {
  const [status, setStatus] = useState<{ connected: boolean; account_login: string | null } | null>(null);
  const [byok, setByok] = useState<{ enabled: boolean; provider: string | null; has_key: boolean } | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [buyingAddon, setBuyingAddon] = useState(false);

  // Add-ons are top-ups on an existing subscription, never sold standalone.
  const isPaid = tier === "pro" || tier === "team";

  useEffect(() => {
    api
      .getByokStatus()
      .then(setByok)
      .catch(() => setByok(null));
  }, []);

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
      title="Add-ons"
      description="Optional top-ups on your existing plan. Each is an explicit one-time purchase — nothing is ever billed automatically when you hit a limit."
    >
      <div className="panel-rise grid items-stretch gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <AddOnCard
          index={0}
          title="Auto-fix pull requests"
          price="$4"
          unit="/ 10 PRs"
          body="Tops up your monthly Fix It allowance when a busy week runs it down."
          bullets={["Cumulative — they stack on your plan's allowance", "Never expire at the end of the period", "One-time charge, no subscription change"]}
          accent="var(--brand)"
          Icon={Wrench}
          state={isPaid ? undefined : { label: "Requires Pro", tone: "muted" }}
          action={
            isPaid ? (
              <Button disabled={buyingAddon} onClick={() => void buyAddon()}>
                {buyingAddon ? "Please wait…" : "Buy +10 PRs"}
              </Button>
            ) : (
              <Button variant="outline" nativeButton={false} render={<Link href="/pricing" />}>
                Upgrade to Pro
              </Button>
            )
          }
        />

        <AddOnCard
          index={1}
          title="Bring your own API key"
          price="$3"
          unit="/ month"
          body="Pay Aevrin a flat platform fee and your model provider directly for tokens."
          bullets={["Supply an Anthropic or Google key", "Scan limits and features stay identical", "Revoke or rotate the key at any time"]}
          accent="var(--chart-3)"
          Icon={KeyRound}
          state={byok?.enabled ? { label: byok.has_key ? "Active" : "Key needed", tone: "ok" } : undefined}
          action={
            byok?.enabled ? (
              <Button variant="outline" nativeButton={false} render={<Link href="/settings/api-keys" />}>
                {byok.has_key ? "Manage key" : "Add key"}
              </Button>
            ) : (
              <Button variant="outline" nativeButton={false} render={<Link href="/pricing" />}>
                Add at checkout
              </Button>
            )
          }
        />

        <AddOnCard
          index={2}
          title="Extra scan credits"
          price="$4"
          unit="/ +25 scans"
          body="Top up CLI, hook, and dashboard scans without changing plan. Pro tops up +100 for $10."
          bullets={["Applies across all three scan buckets", "Today: a spent bucket pauses until it resets", "Or upgrade for a permanently higher limit"]}
          accent="var(--chart-4)"
          Icon={Zap}
          state={{ label: "Not available yet", tone: "muted" }}
          action={<Button variant="outline" disabled>Coming soon</Button>}
        />

        <AddOnCard
          index={3}
          title="GitHub connection"
          price="Included"
          body={
            status === null
              ? "Checking connection status…"
              : status.connected
                ? `Connected as ${status.account_login}. Fix It can open draft pull requests on the repositories you granted.`
                : "Required before Fix It can open pull requests on your behalf."
          }
          bullets={["Scoped to the repositories you pick", "Opens draft PRs only — never merges", "Revocable from GitHub at any time"]}
          accent="var(--chart-1)"
          Icon={GitPullRequest}
          state={status?.connected ? { label: "Connected", tone: "ok" } : undefined}
          action={
            status?.connected ? (
              <Button variant="outline" disabled>
                Connected
              </Button>
            ) : (
              <Button variant="outline" disabled={connecting} onClick={() => void connectGithub()}>
                {connecting ? "Redirecting…" : "Connect GitHub"}
              </Button>
            )
          }
        />
      </div>
    </SectionCard>
  );
}
