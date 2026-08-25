"use client";

import { Fragment, useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Switch } from "@/shared/ui/switch";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/shared/ui/accordion";
import { Check } from "lucide-react";
import { ApiError } from "@/shared/api";
import { billingApi } from "@/entities/billing";
import { createClient } from "@/shared/lib/supabase/client";
import { Reveal } from "@/shared/ui/reveal";

type TierId = "free" | "hobby" | "pro" | "team";

const TEAM_MIN_SEATS = 3;
const BYOK_ADDON_MONTHLY = 3;

interface Tier {
  id: TierId;
  name: string;
  monthly: number; // per-seat for team
  annual: number; // per-month price when billed annually, per-seat for team
  cli: string;
  hook: string;
  dashboard: string;
  retention: string;
  seats: string;
  pdfExport: boolean;
  aiRemediation: boolean;
  aiReviewPerScan: string;
  cta: string;
  popular?: boolean;
  features: string[];
}

const TIERS: Tier[] = [
  {
    id: "free",
    name: "Free",
    monthly: 0,
    annual: 0,
    cli: "5 / month",
    hook: "2 / month",
    dashboard: "5 / month",
    retention: "7 days",
    seats: "1",
    pdfExport: false,
    aiRemediation: true,
    aiReviewPerScan: "40 findings / scan",
    cta: "Start free",
    features: [
      "5 CLI scans / month",
      "2 hook auto-scans / month",
      "5 dashboard scans / month",
      "7-day scan history",
      "AI review on findings: confirmed, false positive, or needs review",
    ],
  },
  {
    id: "hobby",
    name: "Hobby",
    monthly: 9,
    annual: 7,
    cli: "50 / month",
    hook: "20 / month",
    dashboard: "50 / month",
    retention: "90 days",
    seats: "1",
    pdfExport: true,
    aiRemediation: true,
    aiReviewPerScan: "200 findings / scan",
    cta: "Start Hobby",
    features: [
      "50 CLI scans / month",
      "20 hook auto-scans / month",
      "50 dashboard scans / month",
      "90-day scan history",
      "AI review on a stronger model, with a higher per-scan limit",
      "OWASP MCP-mapped report export",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    monthly: 28,
    annual: 24,
    cli: "200 / month",
    hook: "100 / month",
    dashboard: "200 / month",
    retention: "1 year",
    seats: "1",
    pdfExport: true,
    aiRemediation: true,
    aiReviewPerScan: "200 findings / scan",
    cta: "Start Pro",
    popular: true,
    features: [
      "200 CLI scans / month",
      "100 hook auto-scans / month",
      "200 dashboard scans / month",
      "1-year scan history",
      "AI-drafted remediation suggestions",
      "Plain-language scan summary",
      "Upgraded tool-poisoning detection",
    ],
  },
  {
    id: "team",
    name: "Team",
    monthly: 34,
    annual: 28,
    cli: "Usage-based",
    hook: "Usage-based",
    dashboard: "Usage-based",
    retention: "Unlimited",
    seats: "3-seat minimum",
    pdfExport: true,
    aiRemediation: true,
    aiReviewPerScan: "200 findings / scan",
    cta: "Contact us",
    features: [
      "Everything in Pro, usage-based instead of fixed",
      "Org-wide hook policy console: set the block threshold everyone's hook enforces",
      "See everything blocked across the team in one place",
      "SSO and audit log",
      "3-seat minimum, billed per seat",
      "Bring your own model provider key: Aevrin bills the platform, not the tokens",
    ],
  },
];

/* A tick alone tells a screen reader nothing, so inclusion carries a real text
   label. The glyph is decorative and hidden from the accessibility tree. */
function Included() {
  return (
    <>
      <Check className="size-4 text-foreground" aria-hidden="true" />
      <span className="sr-only">Included</span>
    </>
  );
}

function NotIncluded() {
  return (
    <>
      <span aria-hidden="true" className="text-muted-foreground">
        -
      </span>
      <span className="sr-only">Not included</span>
    </>
  );
}

/* Grouped so the table reads as four short comparisons instead of one long
   run of rows. Every value still comes straight off the Tier record. */
const COMPARISON_GROUPS: {
  title: string;
  rows: { label: string; render: (tier: Tier) => ReactNode }[];
}[] = [
  {
    title: "Scan limits",
    rows: [
      { label: "CLI scans", render: (t) => t.cli },
      { label: "Hook auto-scans", render: (t) => t.hook },
      { label: "Dashboard scans", render: (t) => t.dashboard },
    ],
  },
  {
    title: "History and seats",
    rows: [
      { label: "Scan history retained", render: (t) => t.retention },
      { label: "Seats", render: (t) => t.seats },
    ],
  },
  {
    title: "Automation",
    rows: [
      { label: "Compliance PDF export", render: (t) => (t.pdfExport ? <Included /> : <NotIncluded />) },
    ],
  },
  {
    title: "AI review",
    rows: [
      {
        label: "AI remediation suggestions",
        render: (t) => (t.aiRemediation ? <Included /> : <NotIncluded />),
      },
      { label: "AI review per scan", render: (t) => t.aiReviewPerScan },
    ],
  },
];

const FAQ = [
  { q: "Is a card required for the Free plan?", a: "No. Free needs only an account, no billing information at all." },
  {
    q: "What happens when I hit my quota mid-month?",
    a: "That bucket (CLI, hook, or dashboard scans, each counted separately) pauses until it resets on your rolling monthly cycle, or you upgrade. You'll see exactly which bucket and when it resets, in the CLI, the hook, and the dashboard.",
  },
  {
    q: "Does a paid plan renew automatically?",
    a: "No. Each Razorpay checkout buys one monthly or annual cycle. The account returns to Free after the paid-until date unless you purchase another cycle.",
  },
  { q: "Is there a student or nonprofit rate?", a: "A separate student or nonprofit rate is not currently offered." },
  {
    q: "What does bring-your-own-key change?",
    a: "BYOK is a flat monthly platform fee, not a token markup; it never changes your scan limits or feature access, only who pays for the model calls. It can be added at checkout or later from your account settings. Team includes it at no extra charge.",
  },
  {
    q: "How does Team's per-seat pricing work?",
    a: "Team is billed per seat with a 3-seat minimum. Seats are a billing quantity today, not yet a shared multi-user login, every seat purchased raises the account's usage-based limits.",
  },
];

function loadRazorpayScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.getElementById("razorpay-checkout-js")) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.id = "razorpay-checkout-js";
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Could not load Razorpay checkout."));
    document.body.appendChild(script);
  });
}

/**
 * Prices come from GET /billing/pricing, never from constants here, because
 * the same endpoint decides what the order is actually created for. A number
 * hardcoded in this file could drift from what the card is charged.
 *
 * The USD figures in TIERS above remain as the pre-fetch placeholder, so the
 * page renders immediately instead of flashing empty price slots.
 */
type Pricing = {
  currency: string;
  tiers: Record<string, number>;
  byok_addon_per_month: number;
};

/** Minor units (cents/paise) to a whole-unit amount for display. */
function majorUnits(minor: number) {
  return minor / 100;
}

function formatMoney(value: number, currency: string) {
  return new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

export function PricingSection({ headingLevel = "h2" }: { headingLevel?: "h1" | "h2" }) {
  const router = useRouter();
  const [annual, setAnnual] = useState(true);
  // Currency is decided by the server from the caller's location, never
  // chosen here. The override parameter still exists on the API for support
  // to use, but presenting it as a switch invited the obvious question of
  // why a price moves when you press a button.
  const [pricing, setPricing] = useState<Pricing | null>(null);
  const [loadingTier, setLoadingTier] = useState<TierId | null>(null);
  const [teamSeats, setTeamSeats] = useState(TEAM_MIN_SEATS);
  const [byok, setByok] = useState<Record<TierId, boolean>>({ free: false, hobby: false, pro: false, team: false });
  const Heading = headingLevel;

  useEffect(() => {
    let cancelled = false;
    billingApi
      .getPricing()
      .then((p) => {
        if (!cancelled) setPricing(p);
      })
      // A failed fetch leaves the USD placeholders in place, which is the
      // safe direction: the checkout call re-resolves currency server-side
      // anyway, so the worst case is a visitor seeing USD who could have
      // seen INR.
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const currency = pricing?.currency ?? "USD";
  const fmt = (value: number) => formatMoney(value, currency);

  /** Per-month display price, from the server table when it has arrived. */
  function priceFor(tier: Tier, forAnnual: boolean): number {
    if (tier.id === "free") return 0;
    const key = `${tier.id}_${forAnnual ? "annual" : "monthly"}`;
    const amount = pricing?.tiers[key];
    if (amount === undefined) return forAnnual ? tier.annual : tier.monthly;
    // Annual amounts are the full year; the card shows a monthly equivalent.
    return forAnnual ? majorUnits(amount) / 12 : majorUnits(amount);
  }

  const byokMonthly = pricing ? majorUnits(pricing.byok_addon_per_month) : BYOK_ADDON_MONTHLY;

  function savingsFor(tier: Tier): number {
    return (priceFor(tier, false) - priceFor(tier, true)) * 12;
  }

  async function handleCta(tier: Tier) {
    if (tier.id === "free") {
      router.push("/login");
      return;
    }

    const supabase = createClient();
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) {
      router.push(`/login?next=${encodeURIComponent("/pricing")}`);
      return;
    }

    setLoadingTier(tier.id);
    try {
      const cycle = annual ? "annual" : "monthly";
      const { order_id, amount_paise, currency: orderCurrency, razorpay_key_id } = await billingApi.createCheckout(
        tier.id as "hobby" | "pro",
        cycle,
        { seats: 1, byok: byok[tier.id] },
      );
      await loadRazorpayScript();
      type RazorpaySuccess = { razorpay_payment_id: string; razorpay_order_id: string; razorpay_signature: string };
      type RazorpayInstance = { open: () => void; on: (event: string, handler: (resp: unknown) => void) => void };
      const Razorpay = (window as unknown as { Razorpay: new (opts: object) => RazorpayInstance }).Razorpay;
      const checkout = new Razorpay({
        key: razorpay_key_id,
        order_id,
        amount: amount_paise,
        currency: orderCurrency,
        name: "Aevrin",
        description: `${tier.name}, ${cycle}`,
        // Razorpay emails the payment receipt to whatever address it is
        // given here. Without a prefill it has none, so receipts cannot be
        // sent at all no matter what the dashboard is set to. It also saves
        // the customer retyping an address we already know.
        prefill: { email: session.user.email ?? "" },
        theme: { color: "#000000" },
        handler: async (resp: unknown) => {
          const { razorpay_payment_id, razorpay_order_id, razorpay_signature } = resp as RazorpaySuccess;
          try {
            await billingApi.verifyPayment(razorpay_order_id, razorpay_payment_id, razorpay_signature);
            toast.success(`${tier.name} plan activated.`);
            router.push("/dashboard");
          } catch (err) {
            toast.error(err instanceof ApiError ? err.message : "Payment succeeded but activation failed: contact support.");
          }
        },
      });
      checkout.on("payment.failed", () => {
        toast.error("Payment failed. You weren't charged: try again.");
      });
      checkout.open();
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        toast.error("Billing isn't available yet: check back soon.");
      } else {
        toast.error(err instanceof ApiError ? err.message : "Could not start checkout.");
      }
    } finally {
      setLoadingTier(null);
    }
  }

  return (
    <section id="pricing" className="mx-auto max-w-[1500px] px-6 py-24 lg:px-10 xl:px-14">
      <Reveal className="text-center">
        <span className="text-xs font-medium tracking-wide text-brand-text uppercase">Pricing</span>
        <Heading className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
          Simple per-scan-type limits
        </Heading>
        <p className="mt-2 text-muted-foreground">No surprise overages, ever.</p>
        <div className="mt-6 flex items-center justify-center gap-3">
          <span className={annual ? "text-muted-foreground" : ""}>Monthly</span>
          <Switch checked={annual} onCheckedChange={setAnnual} aria-label="Toggle annual billing" />
          <span className={annual ? "" : "text-muted-foreground"}>
            Annual
          </span>
        </div>
      </Reveal>

      <div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
        {TIERS.map((tier, i) => {
          const price = priceFor(tier, annual);
          const seats = tier.id === "team" ? teamSeats : 1;
          const addonMonthly = tier.id !== "free" && tier.id !== "team" && byok[tier.id] ? byokMonthly : 0;
          const totalMonthlyEquivalent = price * seats + addonMonthly;
          return (
            <Reveal key={tier.id} delay={i * 80} className="h-full">
              <div
                className={
                  tier.popular
                    ? "plan-card plan-card-featured flex h-full flex-col"
                    : "plan-card flex h-full flex-col"
                }
              >
                <div className="flex items-center justify-between gap-3">
                  <h3 className="plan-name">{tier.name}</h3>
                  {tier.popular && (
                    <span className="shrink-0 rounded-full bg-brand px-2.5 py-1 text-[11px] font-semibold tracking-[0.08em] text-brand-foreground uppercase">
                      Most popular
                    </span>
                  )}
                </div>

                <div className="mt-6 flex items-baseline gap-1.5">
                  <span className="plan-price">{fmt(totalMonthlyEquivalent)}</span>
                  <span className="text-[15px] text-muted-foreground">
                    /month{tier.id === "team" ? ` (${seats} seats)` : ""}
                  </span>
                </div>
                {/* Fixed slot so every card's button starts from the same line
                    whether or not the tier shows a billing note. */}
                <div className="mt-1.5 min-h-9">
                  {annual && tier.id !== "free" && (
                    <p className="text-[13px] text-muted-foreground">
                      {fmt(totalMonthlyEquivalent * 12)} billed today for one year, save{" "}
                      {fmt(savingsFor(tier) * seats)}
                    </p>
                  )}
                  {!annual && tier.id !== "free" ? (
                    <p className="text-[13px] text-muted-foreground">
                      {fmt(totalMonthlyEquivalent)} billed today for one month
                    </p>
                  ) : null}
                </div>

                <div className="mt-5">
                  {tier.id === "team" ? (
                    <a
                      href="mailto:team@aevrin.net"
                      className="block w-full rounded-[10px] bg-secondary px-4 py-3.5 text-center text-[15px] font-semibold text-secondary-foreground ring-1 ring-border transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                      {tier.cta}
                    </a>
                  ) : (
                    <button
                      type="button"
                      disabled={loadingTier === tier.id}
                      onClick={() => handleCta(tier)}
                      className={
                        tier.popular
                          ? "w-full rounded-[10px] bg-primary px-4 py-3.5 text-[15px] font-semibold text-primary-foreground transition-colors outline-none hover:bg-primary/90 focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
                          : "w-full rounded-[10px] bg-secondary px-4 py-3.5 text-[15px] font-semibold text-secondary-foreground ring-1 ring-border transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
                      }
                    >
                      {loadingTier === tier.id ? "Please wait\u2026" : tier.cta}
                    </button>
                  )}
                </div>

                <div className="mt-6 flex flex-1 flex-col gap-4">
                  {tier.id === "team" && (
                    <div className="flex items-center justify-between rounded-lg ring-1 ring-border px-3 py-2 text-sm">
                      <label htmlFor="team-seats" className="text-muted-foreground">
                        Seats (min {TEAM_MIN_SEATS})
                      </label>
                      <input
                        id="team-seats"
                        type="number"
                        min={TEAM_MIN_SEATS}
                        value={teamSeats}
                        onChange={(e) =>
                          setTeamSeats(Math.max(TEAM_MIN_SEATS, Number(e.target.value) || TEAM_MIN_SEATS))
                        }
                        className="w-16 rounded-md border border-input bg-background px-2 py-1 text-right"
                      />
                    </div>
                  )}
                  {(tier.id === "hobby" || tier.id === "pro") && (
                    <div className="flex items-center justify-between rounded-lg ring-1 ring-border px-3 py-2 text-sm">
                      <label htmlFor={`byok-${tier.id}`} className="text-muted-foreground">
                        Bring your own key (+{fmt(byokMonthly)}/mo)
                      </label>
                      <Switch
                        id={`byok-${tier.id}`}
                        checked={byok[tier.id]}
                        onCheckedChange={(checked) => setByok((prev) => ({ ...prev, [tier.id]: checked }))}
                        aria-label={`Bring your own key for ${tier.name}`}
                      />
                    </div>
                  )}
                  <ul className="flex flex-col gap-2.5 text-[15px] leading-relaxed">
                    {tier.features.map((f) => (
                      <li key={f} className="flex items-start gap-2.5">
                        <Check className="mt-1 size-4 shrink-0 text-muted-foreground" />
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </Reveal>
          );
        })}
      </div>

      <div className="mt-20">
        <h3 className="display-md">Compare plans</h3>
        <div className="mt-8 overflow-x-auto" tabIndex={0} aria-labelledby="plan-comparison-caption">
          <table className="w-full min-w-[720px] border-collapse text-[15px]">
            <caption id="plan-comparison-caption" className="sr-only">
              Feature comparison across the Free, Hobby, Pro and Team plans.
            </caption>
            <thead>
              <tr>
                <th scope="col" className="w-[34%] py-3 pr-4 text-left font-semibold">
                  Feature
                </th>
                {TIERS.map((t) => (
                  <th key={t.id} scope="col" className="py-3 pr-4 text-left font-semibold">
                    {t.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {COMPARISON_GROUPS.map((group) => (
                <Fragment key={group.title}>
                  <tr>
                    {/* Section break: a labelled band is easier to navigate than
                        one undifferentiated run of rows. */}
                    <th
                      scope="colgroup"
                      colSpan={TIERS.length + 1}
                      className="bg-muted px-4 py-2 text-left text-[13px] font-semibold tracking-wide text-muted-foreground uppercase"
                    >
                      {group.title}
                    </th>
                  </tr>
                  {group.rows.map((row) => (
                    <tr key={row.label} className="border-b border-border">
                      <th scope="row" className="py-3.5 pr-4 text-left font-normal text-muted-foreground">
                        {row.label}
                      </th>
                      {TIERS.map((t) => (
                        <td key={t.id} className="py-3.5 pr-4 text-left">
                          {row.render(t)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Filled panels rather than a ruled list, left-aligned over a wide
          measure. Each answer becomes a self-contained block, which scans
          better than dividers when answer lengths vary as much as these do. */}
      <div className="mx-auto mt-20 max-w-4xl">
        <h3 className="display-md">Frequently asked questions</h3>
        <Accordion className="mt-8 flex flex-col gap-2 border-none">
          {FAQ.map((item, i) => (
            <AccordionItem key={i} value={`faq-${i}`} className="faq-row border-none last:border-none">
              <AccordionTrigger className="py-4 text-left text-base font-normal hover:no-underline">
                {item.q}
              </AccordionTrigger>
              <AccordionContent className="pb-4 text-[15px] leading-relaxed text-muted-foreground">
                {item.a}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </section>
  );
}
