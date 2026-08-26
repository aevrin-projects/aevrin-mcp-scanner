"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Archive, ArchiveRestore, Check, CreditCard, Eye, EyeOff, GitPullRequest, KeyRound, Laptop, Receipt, Wrench, Zap } from "lucide-react";
import { ApiError } from "@/shared/api";
import { billingApi, useBillingHistoryPrefs } from "@/entities/billing";
import { githubApi } from "@/entities/github";
import { createClient } from "@/shared/lib/supabase/client";
import { cn } from "@/shared/lib/utils";
import type { Payment, Subscription } from "@/entities/billing";
import type { AccountUsage } from "@/entities/usage";
import { PageHeader, SectionCard } from "@/shared/ui";
import { USAGE_BUCKETS, usageFillColor } from "@/entities/usage";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { Skeleton } from "@/shared/ui/skeleton";
import { formatDate, formatDateTime } from "@/shared/lib/format";
import { usageApi } from "@/entities/usage";

const PAYMENT_TIER_LABEL: Record<Payment["tier"], string> = {
  hobby: "Hobby",
  pro: "Pro",
  team: "Team",
  // No longer sold; historical rows in billing history still render.
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

/** Locale follows the currency, so an Indian customer sees Rs 1,499 rather
 *  than a rupee amount grouped the American way. */
function formatMoney(amountPaise: number, currency: string) {
  return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(amountPaise / 100);
}

type Pricing = {
  currency: string;
  tiers: Record<string, number>;
  byok_addon_per_month: number;
};

/**
 * Everything a price appears in on this page reads from GET /billing/pricing,
 * in the currency this account is actually charged in.
 *
 * These were hardcoded USD strings ("$9 / $7"), which meant a customer who
 * had just paid Rs 499 was shown dollars on the page confirming what they
 * bought, next to a payment history row correctly showing rupees. Two
 * currencies for one purchase reads as a billing error even when the charge
 * was right.
 */
const PLAN_COPY = {
  free: { billing: "No renewal", body: "Five CLI scans, two hook auto-scans, and five dashboard scans each month." },
  hobby: { billing: "One cycle at a time", body: "Monthly / effective annual monthly price, with no automatic renewal." },
  pro: { billing: "One cycle at a time", body: "Monthly / effective annual monthly price, with no automatic renewal." },
  team: { billing: "One cycle at a time", body: "Monthly / effective annual per-seat price, with no automatic renewal." },
} as const;

// Full labels for every bucket: a `capitalize` utility was previously doing
// the work and rendered "cli scans" as "Cli Scans".

export function BillingPage() {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [usage, setUsage] = useState<AccountUsage | null>(null);
  const [payments, setPayments] = useState<Payment[] | null>(null);
  // Captured once on mount: reading the clock during render is impure and
  // would make the period bar jitter on every re-render.
  const [now] = useState(() => Date.now());
  const [pricing, setPricing] = useState<Pricing | null>(null);

  useEffect(() => {
    billingApi
      .getSubscription()
      .then(setSubscription)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not load billing info."));
    usageApi
      .getUsage()
      .then(setUsage)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not load usage info."));
    billingApi
      .getPayments()
      .then(setPayments)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not load billing history."));
    // Silent on failure: prices simply do not render. A toast about pricing
    // on a page that is otherwise working would be noise.
    billingApi.getPricing().then(setPricing).catch(() => {});
  }, []);

  const plan = subscription ? PLAN_COPY[subscription.tier] : null;

  /** Monthly / effective-annual-monthly for the current tier, in the
   *  account's own currency. Null until pricing loads, so nothing renders a
   *  placeholder price that later changes under the reader. */
  const planPrice = (() => {
    if (!subscription || !pricing) return null;
    const tier = subscription.tier;
    if (tier === "free") return formatMoney(0, pricing.currency);
    const monthly = pricing.tiers[`${tier}_monthly`];
    const annual = pricing.tiers[`${tier}_annual`];
    if (monthly === undefined || annual === undefined) return null;
    const suffix = tier === "team" ? " per seat" : "";
    return `${formatMoney(monthly, pricing.currency)} / ${formatMoney(Math.round(annual / 12), pricing.currency)}${suffix}`;
  })();
  const expired = subscription?.tier !== "free" && subscription?.effective_tier === "free";

  // Earliest bucket reset: the only period a Free account actually has.
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
        pretitle="Settings"
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
                    <span className="text-lg text-muted-foreground">{planPrice}</span>
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
                        : "-"}
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
                    : "Nothing is charged automatically; each cycle is an explicit checkout."}
                </p>
              </div>

              <dl className="mt-6 grid gap-4 border-t border-border pt-5 sm:grid-cols-3">
                <div>
                  <dt className="text-xs text-muted-foreground">Renewal</dt>
                  <dd className="mt-1 text-sm font-medium">{plan?.billing ?? "-"}</dd>
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
                Aevrin doesn&apos;t store a card. Each cycle is a one-time Razorpay Standard Checkout; you pick the
                card or method on Razorpay&apos;s own screen every time you pay, and nothing is charged in between.
              </p>
            </div>
          </section>

          <SectionCard title="Usage this period" description="Limits come from the current account and tier configuration.">
            {/* Same hues as the dashboard meters and /usage, so a bucket keeps
                one identity across the product. The bar turns amber near the
                limit and red at it; on a billing page that is the whole point
                of the section, so it should be impossible to miss. */}
            <div className="space-y-3">
              {usage.buckets
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

              {/* Fleet coverage, not a meter: a machine is either watched or
                  it is not, and there is nothing to reset at the anchor date.
                  At the limit this says the machines are NOT MONITORED, never
                  that they are fine -- a gap in coverage is not a clean
                  result, and this page is the last place to imply otherwise. */}
              {(() => {
                const devices = usage.monitored_devices;
                const atLimit = devices.limit !== null && devices.used >= devices.limit;
                return (
                  <div className="rounded-xl border border-border bg-background/80 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <span className="flex min-w-0 items-center gap-2 text-sm font-medium text-foreground">
                        <Laptop aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
                        <span className="truncate">Monitored devices</span>
                      </span>
                      <span className="shrink-0 text-sm tabular-nums text-muted-foreground">
                        {devices.limit === null ? (
                          "Unlimited"
                        ) : (
                          <>
                            <span
                              className={cn(
                                "font-medium",
                                atLimit ? "text-severity-critical" : "text-foreground",
                              )}
                            >
                              {devices.used}
                            </span>{" "}
                            / {devices.limit}
                          </>
                        )}
                      </span>
                    </div>
                    <p className="mt-2.5 text-xs leading-5 text-muted-foreground">
                      {atLimit
                        ? "At your plan limit. A new machine reporting in is not monitored, which is not the same as it being low risk."
                        : "Machines whose agent posture Aevrin tracks. Devices already tracked keep reporting."}
                    </p>
                  </div>
                );
              })()}
            </div>
          </SectionCard>
        </div>
      )}

      {/* Add-ons sit above billing history, not at the page bottom: buying one
          is the main reason anyone opens this page, and a purchase path that
          requires scrolling past invoices is effectively invisible. Shown to
          every tier, hiding them from Free meant nobody could discover they
          exist. */}
      {subscription ? <AddOnsSection tier={subscription.effective_tier} pricing={pricing} /> : null}

      <BillingHistory payments={payments} />

      <SectionCard title="Need something else?" description="Refunds, receipts for accounting, or anything billing-related.">
        <p className="text-sm leading-6 text-muted-foreground">
          Reach the same team that handles product support, no separate billing queue or phone tree.{" "}
          <a href="mailto:support@aevrin.net" className="font-medium text-foreground underline underline-offset-2">
            support@aevrin.net
          </a>
          .
        </p>
      </SectionCard>
    </div>
  );
}

/**
 * Billing history, with the two ways to tidy it: archive one row, or hide the
 * whole table.
 *
 * Neither deletes anything. Every payment stays on the account and in the API
 * response, because these are records of money moving and a control that
 * could make one disappear for good would be a liability rather than a
 * feature. Archiving moves a row behind a toggle, hiding collapses the
 * section, and both are reversible from the header. They are stored in this
 * browser only, so nothing here can reach a charge.
 */
function BillingHistory({ payments }: { payments: Payment[] | null }) {
  const { archived, hidden, archive, restore, restoreAll, setHidden } = useBillingHistoryPrefs();
  // Peeking into the archive lasts for the visit rather than being
  // remembered: someone who opens it to find one receipt does not want the
  // section permanently expanded every time afterwards.
  const [showArchived, setShowArchived] = useState(false);

  const loading = payments === null;
  const active = payments?.filter((payment) => !archived.has(payment.id)) ?? [];
  const archivedRows = payments?.filter((payment) => archived.has(payment.id)) ?? [];
  const rows = showArchived ? archivedRows : active;
  const hasHistory = payments !== null && payments.length > 0;

  return (
    <SectionCard
      title="Billing history"
      description="Every checkout this account has started, most recent first, including ones that didn't complete, so a missing charge is never a mystery."
      action={
        hasHistory ? (
          <Button variant="ghost" size="sm" onClick={() => setHidden(!hidden)}>
            {hidden ? <Eye aria-hidden="true" /> : <EyeOff aria-hidden="true" />}
            {hidden ? "Show" : "Hide"}
          </Button>
        ) : null
      }
    >
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-14 rounded-xl" />
          ))}
        </div>
      ) : hidden ? (
        <p className="rounded-xl border border-dashed border-border px-5 py-6 text-center text-sm text-muted-foreground">
          Billing history is hidden on this device. {payments.length}{" "}
          {payments.length === 1 ? "payment is" : "payments are"} still on the account: use Show above to bring the
          table back.
        </p>
      ) : payments.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border px-5 py-10 text-center">
          <Receipt className="size-6 text-muted-foreground" />
          <p className="text-sm font-medium">No payments yet</p>
          <p className="max-w-sm text-sm text-muted-foreground">
            Nothing has been charged on this account. Free needs no payment method at all.
          </p>
        </div>
      ) : (
        <>
          {archivedRows.length > 0 ? (
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Button
                variant={showArchived ? "secondary" : "outline"}
                size="sm"
                aria-pressed={showArchived}
                onClick={() => setShowArchived(!showArchived)}
              >
                <Archive aria-hidden="true" />
                {showArchived ? "Back to active" : `Archived (${archivedRows.length})`}
              </Button>
              {showArchived ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    restoreAll();
                    setShowArchived(false);
                  }}
                >
                  <ArchiveRestore aria-hidden="true" />
                  Restore all
                </Button>
              ) : null}
            </div>
          ) : null}

          {rows.length === 0 ? (
            <p className="rounded-xl border border-dashed border-border px-5 py-6 text-center text-sm text-muted-foreground">
              Every payment on this account is archived. Open Archived ({archivedRows.length}) above to see them.
            </p>
          ) : (
            <div
              className="overflow-x-auto"
              tabIndex={0}
              aria-label={showArchived ? "Archived billing history" : "Billing history"}
            >
              <table className="w-full min-w-[640px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-[0.08em] text-muted-foreground">
                    <th className="py-2 pr-4 font-medium">Date</th>
                    <th className="py-2 pr-4 font-medium">Plan</th>
                    <th className="py-2 pr-4 font-medium">Cycle</th>
                    <th className="py-2 pr-4 font-medium">Amount</th>
                    <th className="py-2 pr-4 font-medium">Status</th>
                    <th className="py-2 font-medium">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((payment) => (
                    <tr key={payment.id} className="border-b border-border/50 last:border-0">
                      <td className="py-3 pr-4 text-muted-foreground">{formatDate(payment.created_at)}</td>
                      <td className="py-3 pr-4">
                        {PAYMENT_TIER_LABEL[payment.tier]}
                        {payment.seats > 1 ? ` · ${payment.seats} seats` : ""}
                        {payment.byok ? " · BYOK" : ""}
                      </td>
                      <td className="py-3 pr-4 capitalize text-muted-foreground">{payment.cycle}</td>
                      <td className="py-3 pr-4 font-medium">{formatMoney(payment.amount_paise, payment.currency)}</td>
                      <td className="py-3 pr-4">
                        <Badge variant="outline" className={PAYMENT_STATUS_STYLE[payment.status]}>
                          {PAYMENT_STATUS_LABEL[payment.status]}
                        </Badge>
                      </td>
                      <td className="py-3 text-right">
                        {/* Labelled with the row it acts on, so a screen
                            reader hears which payment is being put away
                            rather than six identical "Archive" buttons. */}
                        <Button
                          variant="ghost"
                          size="sm"
                          aria-label={`${showArchived ? "Restore" : "Archive"} the ${formatDate(
                            payment.created_at,
                          )} ${PAYMENT_TIER_LABEL[payment.tier]} payment`}
                          onClick={() => {
                            if (!showArchived) {
                              archive(payment.id);
                              return;
                            }
                            restore(payment.id);
                            // Restoring the last archived row would otherwise
                            // leave the view stuck on an empty archive with no
                            // toggle left to leave it by.
                            if (archivedRows.length === 1) setShowArchived(false);
                          }}
                        >
                          {showArchived ? <ArchiveRestore aria-hidden="true" /> : <Archive aria-hidden="true" />}
                          {showArchived ? "Restore" : "Archive"}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </SectionCard>
  );
}

// Each of these is a genuinely different outcome. They were previously all
// reported as "cancelled", which told someone who had just granted access
// that they hadn't, the exact confusion behind "I approved it and nothing
// updated".
const GITHUB_CALLBACK_MESSAGE: Record<string, { message: string; ok: boolean }> = {
  connected: { message: "GitHub connected: Aevrin can now scan the repositories you granted.", ok: true },
  cancelled: { message: "GitHub connection cancelled; nothing was granted.", ok: false },
  invalid_state: { message: "That connection link expired, try connecting again.", ok: false },
  authorized_not_installed: {
    message:
      "You authorized Aevrin but didn't finish installing it, so it has no repository access yet. Use Connect GitHub and pick the repositories on the install screen.",
    ok: false,
  },
  needs_relink: {
    message:
      "Installed on GitHub, but it arrived without the link that ties it to this Aevrin account. Click Connect GitHub here to finish; it won't ask for access again.",
    ok: false,
  },
  updated: {
    message: "GitHub access updated: your repository list here now matches what you granted.",
    ok: true,
  },
  approval_pending: {
    message: "Requested: an owner of that GitHub organization has to approve the install before it takes effect.",
    ok: false,
  },
  error: { message: "Could not complete the GitHub connection, try again.", ok: false },
};

/**
 * One add-on, presented as something you buy: an icon in its own tinted
 * chip, the price as the largest thing in the card, what you actually get as
 * a short list, and a full-width CTA pinned to the bottom so every card's
 * button lines up. The previous version was a text row with the price as a
 * gray chip; it read as documentation, not as a product.
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

function AddOnsSection({
  tier,
  pricing,
}: {
  tier: Subscription["effective_tier"];
  pricing: Pricing | null;
}) {
  const [status, setStatus] = useState<{ connected: boolean; account_login: string | null } | null>(null);
  const [byok, setByok] = useState<{ enabled: boolean; provider: string | null; has_key: boolean } | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [buyingByok, setBuyingByok] = useState(false);

  // Em dash while pricing loads rather than a USD guess that changes to
  // rupees a moment later.
  const byokPrice = pricing ? formatMoney(pricing.byok_addon_per_month, pricing.currency) : "-";


  useEffect(() => {
    billingApi
      .getByokStatus()
      .then(setByok)
      .catch(() => setByok(null));
  }, []);

  useEffect(() => {
    githubApi
      .getStatus()
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
      const { url } = await githubApi.getInstallUrl();
      window.location.href = url;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not start GitHub connection.");
      setConnecting(false);
    }
  }

  /** Shared by both add-on purchases: the only differences were which
   *  endpoint to call and what to say afterwards. */
  async function runAddonCheckout(
    createOrder: () => Promise<{ order_id: string; amount_paise: number; currency: string; razorpay_key_id: string }>,
    description: string,
    successMessage: string,
    setBusy: (busy: boolean) => void,
  ) {
    setBusy(true);
    try {
      // Read straight from the session rather than holding it in state: this
      // runs once per purchase, and a stale email on a receipt is worse than
      // one extra call.
      const {
        data: { session },
      } = await createClient().auth.getSession();
      const customerEmail = session?.user.email ?? "";

      const { order_id, amount_paise, currency, razorpay_key_id } = await createOrder();
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
        description,
        // See the pricing page: without an address here Razorpay has
        // nowhere to send the payment receipt.
        prefill: { email: customerEmail },
        theme: { color: "#000000" },
        handler: async (resp: unknown) => {
          const { razorpay_payment_id, razorpay_order_id, razorpay_signature } = resp as RazorpaySuccess;
          try {
            await billingApi.verifyPayment(razorpay_order_id, razorpay_payment_id, razorpay_signature);
            toast.success(successMessage);
            // Re-read rather than assume: the add-on state shown on this
            // card comes from the server, and guessing it here would show
            // "Active" for a grant that failed to apply.
            billingApi.getByokStatus().then(setByok).catch(() => {});
          } catch (err) {
            toast.error(err instanceof ApiError ? err.message : "Payment succeeded but activation failed: contact support.");
          }
        },
      });
      checkout.on("payment.failed", () => toast.error("Payment failed. You weren't charged: try again."));
      checkout.open();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not start checkout.");
    } finally {
      setBusy(false);
    }
  }

  const buyByokAddon = () =>
    void runAddonCheckout(
      billingApi.createByokAddonCheckout,
      "Bring your own API key",
      "Bring-your-own-key is active. Add your provider key in API keys.",
      setBuyingByok,
    );

  return (
    <SectionCard
      title="Add-ons"
      description="Optional top-ups on your existing plan. Each is an explicit one-time purchase; nothing is ever billed automatically when you hit a limit."
    >
      <div className="panel-rise grid items-stretch gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <AddOnCard
          index={0}
          title="Bring your own API key"
          price={byokPrice}
          unit="/ month"
          body="Pay Aevrin a flat platform fee and your model provider directly for tokens."
          bullets={["Supply your own model provider key", "Scan limits and features stay identical", "Revoke or rotate the key at any time"]}
          accent="var(--chart-3)"
          Icon={KeyRound}
          state={byok?.enabled ? { label: byok.has_key ? "Active" : "Key needed", tone: "ok" } : undefined}
          action={
            byok?.enabled ? (
              <Button variant="outline" nativeButton={false} render={<Link href="/settings/api-keys" />}>
                {byok.has_key ? "Manage key" : "Add key"}
              </Button>
            ) : tier === "free" ? (
              // BYOK needs an active paid plan, so there is genuinely
              // nothing to buy here yet.
              <Button variant="outline" nativeButton={false} render={<Link href="/pricing" />}>
                Requires a paid plan
              </Button>
            ) : (
              // Previously this bounced to /pricing, which meant buying
              // another whole plan cycle just to add a $3 flag.
              <Button variant="outline" disabled={buyingByok} onClick={buyByokAddon}>
                {buyingByok ? "Please wait…" : "Add for " + byokPrice}
              </Button>
            )
          }
        />

        <AddOnCard
          index={1}
          title="Extra scan credits"
          price="-"
          unit="/ +25 scans"
          body="Top up CLI, hook, and dashboard scans without changing plan."
          bullets={["Applies across all three scan buckets", "Today: a spent bucket pauses until it resets", "Or upgrade for a permanently higher limit"]}
          accent="var(--chart-4)"
          Icon={Zap}
          state={{ label: "Not available yet", tone: "muted" }}
          action={<Button variant="outline" disabled>Coming soon</Button>}
        />

        <AddOnCard
          index={2}
          title="GitHub connection"
          price="Included"
          body={
            status === null
              ? "Checking connection status…"
              : status.connected
                ? `Connected as ${status.account_login}. Aevrin can scan the repositories you granted.`
                : "Required before Aevrin can scan a private repository on your behalf."
          }
          bullets={["Scoped to the repositories you pick", "Opens draft PRs only; never merges", "Revocable from GitHub at any time"]}
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
