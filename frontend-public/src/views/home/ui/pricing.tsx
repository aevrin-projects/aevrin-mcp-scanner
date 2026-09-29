"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Check } from "lucide-react";
import { Switch } from "@/shared/ui/switch";
import { Reveal } from "@/shared/ui/reveal";
import { SectionHeader } from "./section-header";

/**
 * Pricing, in the Nguyen card structure: a thin shell around an inner panel
 * (name, badge, price, one line, a full-width action), then a labelled
 * divider and what the plan includes.
 *
 * Prices. The first render is the canonical USD table, in cents, copied from
 * `_PRICE_CENTS` in backend/api/aevrin_api/controllers/billing_controller.py;
 * if that table changes, change this one. On the client the page then asks
 * GET /billing/pricing, the same endpoint the checkout resolves currency with,
 * and replaces the amounts and currency (INR for India, otherwise USD). If the
 * request fails the USD figures stay, silently: checkout re-resolves the
 * currency on the server anyway, so the worst case is a visitor in India
 * seeing dollars.
 *
 * Savings are computed per plan from those amounts (monthly x 12 minus the
 * annual charge). They differ by plan (Hobby 22%, Pro 14%, Team 18% in USD),
 * so there is deliberately no single "save N%" tag.
 *
 * Limits are the seeded `tier_limits` rows (docs/features/BILLING.md) and the
 * AI review caps in `services/triage.py`. Seats: `TEAM_MIN_SEATS` and
 * `TEAM_MAX_SEATS` in backend/api/aevrin_api/schemas/billing.py.
 *
 * Checkout lives in the app, so paid plans link to the matching card on the
 * app's pricing page (`id="plan-<tier>"` there) and Free goes to sign-in.
 */

const API_PRICING_URL = "https://api.mcp.aevrin.net/billing/pricing";
const APP_ORIGIN = "https://app.mcp.aevrin.net";

type PaidTier = "hobby" | "pro" | "team";
type Pricing = { currency: string; tiers: Record<string, number> };

const STATIC_PRICING: Pricing = {
  currency: "USD",
  tiers: {
    hobby_monthly: 900,
    hobby_annual: 8_400,
    pro_monthly: 2_800,
    pro_annual: 28_800,
    team_monthly: 3_400,
    team_annual: 33_600,
  },
};

const TEAM_MIN_SEATS = 3;
const TEAM_MAX_SEATS = 500;

type Plan = {
  id: "free" | PaidTier;
  name: string;
  badge?: string;
  summary: string;
  cta: string;
  href: string;
  includes: string[];
};

const PLANS: Plan[] = [
  {
    id: "free",
    name: "Free",
    badge: "No card",
    summary: "For trying Aevrin on the servers you use.",
    cta: "Start free",
    href: `${APP_ORIGIN}/login`,
    includes: [
      "5 CLI scans a month",
      "5 dashboard scans a month",
      "2 Claude Code hook scans a month",
      "10 agent scans on 1 device",
      "AI review of up to 40 findings per scan",
    ],
  },
  {
    id: "hobby",
    name: "Hobby",
    summary: "For one developer checking servers as they go.",
    cta: "Choose Hobby",
    href: `${APP_ORIGIN}/pricing#plan-hobby`,
    includes: [
      "50 CLI scans a month",
      "50 dashboard scans a month",
      "20 Claude Code hook scans a month",
      "100 agent scans on up to 3 devices",
      "AI review of up to 200 findings per scan",
      "Printable report export",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    summary: "For daily use, in the terminal and in CI.",
    cta: "Choose Pro",
    href: `${APP_ORIGIN}/pricing#plan-pro`,
    includes: [
      "200 CLI scans a month",
      "200 dashboard scans a month",
      "100 Claude Code hook scans a month",
      "400 agent scans on up to 10 devices",
      "AI review of up to 200 findings per scan",
      "Printable report export",
    ],
  },
  {
    id: "team",
    name: "Team",
    badge: "Per seat",
    summary: `For a workspace of ${TEAM_MIN_SEATS} to ${TEAM_MAX_SEATS} people.`,
    cta: "Choose Team",
    href: `${APP_ORIGIN}/pricing#plan-team`,
    includes: [
      "No monthly scan cap, no device cap",
      "Everyone in the workspace gets Team limits",
      "Members see the workspace's scans, findings and agents",
      "Roles you define for what each member may do",
      "AI review of up to 200 findings per scan",
      "Printable report export",
    ],
  },
];

function formatMoney(minorUnits: number, currency: string) {
  return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(minorUnits / 100);
}

function isPricing(value: unknown): value is Pricing {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<Pricing>;
  if (typeof candidate.currency !== "string" || !/^[A-Z]{3}$/.test(candidate.currency)) return false;
  const tiers = candidate.tiers;
  if (!tiers || typeof tiers !== "object") return false;
  return Object.keys(STATIC_PRICING.tiers).every(
    (key) => Number.isInteger((tiers as Record<string, unknown>)[key]) && (tiers as Record<string, number>)[key] > 0,
  );
}

function Price({ value }: { value: string }) {
  // One markup either way, so the server HTML and a reduced-motion client
  // hydrate identically; reduced motion only drops the cross-fade.
  const reduceMotion = useReducedMotion();
  return (
    <AnimatePresence mode="popLayout" initial={false}>
      <motion.span
        key={value}
        className="inline-block"
        initial={reduceMotion ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={reduceMotion ? { opacity: 0, transition: { duration: 0 } } : { opacity: 0, y: -8 }}
        transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
      >
        {value}
      </motion.span>
    </AnimatePresence>
  );
}

export function Pricing() {
  const [annual, setAnnual] = useState(true);
  const [pricing, setPricing] = useState<Pricing>(STATIC_PRICING);
  const switchId = useId();

  useEffect(() => {
    const controller = new AbortController();
    fetch(API_PRICING_URL, { signal: controller.signal, credentials: "omit" })
      .then((response) => (response.ok ? response.json() : null))
      .then((body: unknown) => {
        if (isPricing(body)) setPricing(body);
      })
      // Any failure keeps the static USD table; see the comment above.
      .catch(() => {});
    return () => controller.abort();
  }, []);

  const money = (minor: number) => formatMoney(minor, pricing.currency);

  return (
    <section id="pricing" aria-labelledby="pricing-title" className="mk-section">
      <div className="mk-container">
        <SectionHeader
          id="pricing-title"
          eyebrow="Pricing"
          centered
          title="Start free. Pay when you scan more."
          lede="Every plan includes AI review of findings. A paid plan buys one month or one year, and nothing renews on its own."
        />

        <Reveal className="mt-8 flex items-center justify-center gap-3 text-sm">
          <span className={annual ? "text-[var(--mk-muted)]" : "font-medium text-[var(--mk-fg-strong)]"} aria-hidden="true">
            Monthly
          </span>
          <Switch id={switchId} checked={annual} onCheckedChange={setAnnual} aria-label="Annual billing" />
          <span className={annual ? "font-medium text-[var(--mk-fg-strong)]" : "text-[var(--mk-muted)]"} aria-hidden="true">
            Annual
          </span>
        </Reveal>

        <ul className="mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {PLANS.map((plan, index) => {
            const paid = plan.id !== "free";
            const monthly = paid ? pricing.tiers[`${plan.id}_monthly`] : 0;
            const yearly = paid ? pricing.tiers[`${plan.id}_annual`] : 0;
            const shown = annual ? Math.round(yearly / 12) : monthly;
            const saving = monthly * 12 - yearly;
            const perSeat = plan.id === "team";

            let note: string;
            if (!paid) note = "No card needed, nothing to cancel.";
            else if (annual)
              note = perSeat
                ? `${money(yearly)} a seat, billed once for 12 months. Save ${money(saving)} a seat.`
                : `${money(yearly)} billed once for 12 months. Save ${money(saving)} a year.`;
            else note = `${money(monthly)}${perSeat ? " a seat," : ""} billed once for one month.`;

            return (
              <li key={plan.id}>
                <Reveal delay={index * 80} className="h-full">
                  <article
                    aria-labelledby={`plan-${plan.id}-name`}
                    className="flex h-full flex-col rounded-[20px] border border-[var(--mk-line)] bg-[var(--mk-bg)] p-1.5 shadow-xl shadow-black/5"
                  >
                    <div className="rounded-[14px] border border-[var(--mk-line)] bg-[var(--mk-illustration)] p-5">
                      <div className="flex items-center gap-2">
                        <h3 id={`plan-${plan.id}-name`} className="text-[15px] font-medium text-[var(--mk-fg)]">
                          {plan.name}
                        </h3>
                        {plan.badge ? (
                          <span className="rounded-full border border-[var(--mk-line)] bg-[var(--mk-bg)] px-2 py-0.5 text-[11px] font-medium text-[var(--mk-fg)]">
                            {plan.badge}
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-3 flex items-baseline gap-1.5">
                        <span className="text-3xl font-bold tracking-tight text-[var(--mk-fg-strong)] tabular-nums">
                          <Price value={money(shown)} />
                        </span>
                        <span className="text-sm text-[var(--mk-muted)]">{perSeat ? "per seat / month" : "/ month"}</span>
                      </p>
                      <p className="mt-1 text-[13px] md:min-h-10 leading-5 text-[var(--mk-muted)]">{note}</p>
                      <p className="mt-3 text-sm leading-5 md:min-h-10 text-[var(--mk-fg)]">{plan.summary}</p>
                      <Link
                        href={plan.href}
                        className={`mk-btn mk-btn-pill mt-5 w-full ${plan.id === "free" ? "mk-btn-solid" : "mk-btn-outline"}`}
                      >
                        {plan.cta}
                        <span className="sr-only">{paid ? `, ${annual ? "annual" : "monthly"} billing` : ""}</span>
                      </Link>
                    </div>

                    <div className="flex flex-1 flex-col px-4 pt-5 pb-4">
                      <p className="flex items-center gap-3 text-[13px] text-[var(--mk-muted)]">
                        <span aria-hidden="true" className="h-px flex-1 bg-[var(--mk-line)]" />
                        Includes
                        <span aria-hidden="true" className="h-px flex-1 bg-[var(--mk-line)]" />
                      </p>
                      <ul className="mt-4 space-y-2.5 text-sm leading-5 text-[var(--mk-fg)]">
                        {plan.includes.map((line) => (
                          <li key={line} className="flex gap-2.5">
                            <Check className="mt-0.5 size-4 shrink-0 text-[var(--mk-muted)]" aria-hidden="true" />
                            <span>{line}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </article>
                </Reveal>
              </li>
            );
          })}
        </ul>

        <p className="mt-8 text-center text-sm text-[var(--mk-muted)]">
          No card for Free. Paid plans do not renew on their own.{" "}
          <Link
            href={`${APP_ORIGIN}/pricing`}
            className="text-[var(--mk-fg)] underline decoration-[var(--mk-line-strong)] underline-offset-4 hover:decoration-current"
          >
            Compare every limit
          </Link>
        </p>
      </div>
    </section>
  );
}
