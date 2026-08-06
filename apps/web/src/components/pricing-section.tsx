"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Check } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { Reveal } from "@/components/reveal";

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
  autoFixPrs: string;
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
    autoFixPrs: "—",
    pdfExport: false,
    aiRemediation: true,
    aiReviewPerScan: "40 findings / scan",
    cta: "Start free",
    features: [
      "5 CLI scans / month",
      "2 hook auto-scans / month",
      "5 dashboard scans / month",
      "7-day scan history",
      "AI review on findings — confirmed, false positive, or needs review",
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
    autoFixPrs: "—",
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
    monthly: 34,
    annual: 29,
    cli: "200 / month",
    hook: "100 / month",
    dashboard: "200 / month",
    retention: "1 year",
    seats: "1",
    autoFixPrs: "15 / month",
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
      "15 auto-fix pull requests / month — drafts a fix, re-runs the scanner to confirm it, opens a draft PR",
      "AI-drafted remediation suggestions",
      "Plain-language scan summary",
      "Upgraded tool-poisoning detection",
    ],
  },
  {
    id: "team",
    name: "Team",
    monthly: 40,
    annual: 33,
    cli: "Usage-based",
    hook: "Usage-based",
    dashboard: "Usage-based",
    retention: "Unlimited",
    seats: "3-seat minimum",
    autoFixPrs: "15 / month / seat",
    pdfExport: true,
    aiRemediation: true,
    aiReviewPerScan: "200 findings / scan",
    cta: "Contact us",
    features: [
      "Everything in Pro, usage-based instead of fixed",
      "15 auto-fix pull requests / month / seat, pooled across the team",
      "Org-wide hook policy console — set the block threshold everyone's hook enforces",
      "See everything blocked across the team in one place",
      "SSO and audit log",
      "3-seat minimum, billed per seat",
      "Bring your own model provider key — Aevrin bills the platform, not the tokens",
    ],
  },
];

const FAQ = [
  { q: "Is a card required for the Free plan?", a: "No. Free needs only an account — no billing information at all." },
  {
    q: "What happens when I hit my quota mid-month?",
    a: "That bucket (CLI, hook, or dashboard scans — each counted separately) pauses until it resets on your rolling monthly cycle, or you upgrade. You'll see exactly which bucket and when it resets, in the CLI, the hook, and the dashboard.",
  },
  {
    q: "Does a paid plan renew automatically?",
    a: "No. Each Razorpay checkout buys one monthly or annual cycle. The account returns to Free after the paid-until date unless you purchase another cycle.",
  },
  { q: "Is there a student or nonprofit rate?", a: "A separate student or nonprofit rate is not currently offered." },
  {
    q: "What does bring-your-own-key change?",
    a: `BYOK is a flat +$${BYOK_ADDON_MONTHLY}/month platform fee, not a token markup — it never changes your scan limits or feature access, only who pays for the model calls. Team includes it at no extra charge.`,
  },
  {
    q: "How does Team's per-seat pricing work?",
    a: "Team is billed per seat with a 3-seat minimum. Seats are a billing quantity today, not yet a shared multi-user login — every seat purchased raises the account's usage-based limits.",
  },
  {
    q: "What happens when I use all 15 auto-fix PRs in a month?",
    a: "Fix It pauses until your allowance resets, or you buy +10 more PRs for $4 from your account settings — a one-time, explicit purchase, never an automatic overage charge. The add-on requires an active Pro or Team subscription and is never sold on its own.",
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

function formatUsd(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function PricingSection({ headingLevel = "h2" }: { headingLevel?: "h1" | "h2" }) {
  const router = useRouter();
  const [annual, setAnnual] = useState(true);
  const [loadingTier, setLoadingTier] = useState<TierId | null>(null);
  const [teamSeats, setTeamSeats] = useState(TEAM_MIN_SEATS);
  const [byok, setByok] = useState<Record<TierId, boolean>>({ free: false, hobby: false, pro: false, team: false });
  const Heading = headingLevel;

  function savingsFor(tier: Tier): number {
    return (tier.monthly - tier.annual) * 12;
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
      const { order_id, amount_paise, currency, razorpay_key_id } = await api.createCheckout(
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
        currency,
        name: "Aevrin",
        description: `${tier.name} — ${cycle}`,
        theme: { color: "#000000" },
        handler: async (resp: unknown) => {
          const { razorpay_payment_id, razorpay_order_id, razorpay_signature } = resp as RazorpaySuccess;
          try {
            await api.verifyPayment(razorpay_order_id, razorpay_payment_id, razorpay_signature);
            toast.success(`${tier.name} plan activated.`);
            router.push("/dashboard");
          } catch (err) {
            toast.error(err instanceof ApiError ? err.message : "Payment succeeded but activation failed — contact support.");
          }
        },
      });
      checkout.on("payment.failed", () => {
        toast.error("Payment failed. You weren't charged — try again.");
      });
      checkout.open();
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        toast.error("Billing isn't available yet — check back soon.");
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

      <div className="mt-10 grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {TIERS.map((tier, i) => {
          const price = annual ? tier.annual : tier.monthly;
          const seats = tier.id === "team" ? teamSeats : 1;
          const addonMonthly = tier.id !== "free" && tier.id !== "team" && byok[tier.id] ? BYOK_ADDON_MONTHLY : 0;
          const totalMonthlyEquivalent = price * seats + addonMonthly;
          return (
            <Reveal key={tier.id} delay={i * 80} className="h-full">
              <Card
                className={
                  tier.popular ? "h-full border-brand shadow-lg shadow-brand/20 sm:scale-105" : "h-full"
                }
              >
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>{tier.name}</CardTitle>
                    {tier.popular && (
                      <Badge className="border-transparent bg-brand text-brand-foreground">Most popular</Badge>
                    )}
                  </div>
                  <div className="flex items-baseline gap-1 pt-2">
                    <span className="text-3xl font-semibold">{formatUsd(totalMonthlyEquivalent)}</span>
                    <span className="text-sm text-muted-foreground">
                      /month{tier.id === "team" ? ` (${seats} seats)` : ""}
                    </span>
                  </div>
                  {annual && tier.id !== "free" && (
                    <p className="text-xs text-muted-foreground">
                      {formatUsd(totalMonthlyEquivalent * 12)} billed today for one year — save{" "}
                      {formatUsd(savingsFor(tier) * seats)}
                    </p>
                  )}
                  {!annual && tier.id !== "free" ? (
                    <p className="text-xs text-muted-foreground">
                      {formatUsd(totalMonthlyEquivalent)} billed today for one month
                    </p>
                  ) : null}
                </CardHeader>
                <CardContent className="flex flex-col gap-4">
                  {tier.id === "team" && (
                    <div className="flex items-center justify-between rounded-lg border border-border/80 px-3 py-2 text-sm">
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
                        className="w-16 rounded-md border border-border bg-background px-2 py-1 text-right"
                      />
                    </div>
                  )}
                  {(tier.id === "hobby" || tier.id === "pro") && (
                    <div className="flex items-center justify-between rounded-lg border border-border/80 px-3 py-2 text-sm">
                      <label htmlFor={`byok-${tier.id}`} className="text-muted-foreground">
                        Bring your own key (+{formatUsd(BYOK_ADDON_MONTHLY)}/mo)
                      </label>
                      <Switch
                        id={`byok-${tier.id}`}
                        checked={byok[tier.id]}
                        onCheckedChange={(checked) => setByok((prev) => ({ ...prev, [tier.id]: checked }))}
                        aria-label={`Bring your own key for ${tier.name}`}
                      />
                    </div>
                  )}
                  <ul className="flex flex-col gap-2 text-sm">
                    {tier.features.map((f) => (
                      <li key={f} className="flex items-start gap-2">
                        <Check className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>
                  {tier.id === "team" ? (
                    <a href="mailto:team@aevrin.net" className={buttonVariants({ className: "w-full", variant: "outline" })}>
                      {tier.cta}
                    </a>
                  ) : (
                    <Button
                      className="w-full"
                      variant={tier.popular ? "default" : "outline"}
                      disabled={loadingTier === tier.id}
                      onClick={() => handleCta(tier)}
                    >
                      {loadingTier === tier.id ? "Please wait…" : tier.cta}
                    </Button>
                  )}
                </CardContent>
              </Card>
            </Reveal>
          );
        })}
      </div>

      <div className="mt-16 overflow-x-auto" tabIndex={0} aria-label="Pricing comparison table">
        <table className="w-full min-w-[680px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="py-3 font-medium text-muted-foreground">Feature</th>
              {TIERS.map((t) => (
                <th key={t.id} className="py-3 text-center font-medium">
                  {t.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[
              { label: "CLI scans", key: "cli" as const },
              { label: "Hook auto-scans", key: "hook" as const },
              { label: "Dashboard scans", key: "dashboard" as const },
              { label: "Scan history retained", key: "retention" as const },
              { label: "Seats", key: "seats" as const },
              { label: "Auto-fix pull requests", key: "autoFixPrs" as const },
            ].map((row) => (
              <tr key={row.key} className="border-b border-border/50">
                <td className="py-3 text-muted-foreground">{row.label}</td>
                {TIERS.map((t) => (
                  <td key={t.id} className="py-3 text-center">
                    {t[row.key]}
                  </td>
                ))}
              </tr>
            ))}
            <tr className="border-b border-border/50">
              <td className="py-3 text-muted-foreground">Compliance PDF export</td>
              {TIERS.map((t) => (
                <td key={t.id} className="py-3 text-center">
                  {t.pdfExport ? <Check className="mx-auto size-4" /> : "—"}
                </td>
              ))}
            </tr>
            <tr>
              <td className="py-3 text-muted-foreground">AI remediation suggestions</td>
              {TIERS.map((t) => (
                <td key={t.id} className="py-3 text-center">
                  {t.aiRemediation ? <Check className="mx-auto size-4" /> : "—"}
                </td>
              ))}
            </tr>
            <tr>
              <td className="py-3 text-muted-foreground">AI review per scan</td>
              {TIERS.map((t) => (
                <td key={t.id} className="py-3 text-center">
                  {t.aiReviewPerScan}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="mx-auto mt-16 max-w-2xl">
        <h3 className="text-center text-lg font-medium">Frequently asked questions</h3>
        <Accordion className="mt-6">
          {FAQ.map((item, i) => (
            <AccordionItem key={i} value={`faq-${i}`}>
              <AccordionTrigger>{item.q}</AccordionTrigger>
              <AccordionContent>{item.a}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>

      <p className="mt-8 text-center text-xs leading-5 text-muted-foreground">
        Prices are charged in US dollars through Razorpay. Taxes may apply. Aevrin pauses new scans at the configured limit and does not create automatic overage charges.
      </p>
    </section>
  );
}
