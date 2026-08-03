"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Check } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { Reveal } from "@/components/reveal";

type TierId = "free" | "hobby" | "team";

interface Tier {
  id: TierId;
  name: string;
  monthly: number;
  annual: number; // per-month price when billed annually
  cli: string;
  hook: string;
  dashboard: string;
  retention: string;
  seats: string;
  pdfExport: boolean;
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
    cta: "Start free",
    features: [
      "5 CLI scans / month",
      "2 hook auto-scans / month",
      "5 dashboard scans / month",
      "7-day scan history",
      "Community support",
    ],
  },
  {
    id: "hobby",
    name: "Hobby",
    monthly: 15,
    annual: 12,
    cli: "50 / month",
    hook: "20 / month",
    dashboard: "50 / month",
    retention: "90 days",
    seats: "1",
    pdfExport: true,
    cta: "Start Hobby",
    popular: true,
    features: [
      "50 CLI scans / month",
      "20 hook auto-scans / month",
      "50 dashboard scans / month",
      "90-day scan history",
      "Compliance report export (PDF)",
      "Email support",
    ],
  },
  {
    id: "team",
    name: "Team",
    monthly: 59,
    annual: 49,
    cli: "Unlimited",
    hook: "Unlimited",
    dashboard: "Unlimited",
    retention: "Unlimited",
    seats: "5 included",
    pdfExport: true,
    cta: "Start Team",
    features: [
      "Unlimited CLI scans",
      "Unlimited hook auto-scans",
      "Unlimited dashboard scans",
      "Unlimited scan history",
      "Compliance report export (PDF)",
      "5 seats included, then per-seat",
      "Priority support",
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
    q: "Can I downgrade later?",
    a: "Yes, any time. Your existing scan history isn't deleted immediately — it's kept through a grace period and only trimmed to the new plan's retention window afterward.",
  },
  { q: "Is there a student or nonprofit rate?", a: "Not yet — email us and we'll work something out in the meantime." },
  {
    q: "How are seats counted on Team?",
    a: "Team includes 5 seats. Additional seats beyond that are billed per-seat.",
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

export function PricingSection() {
  const router = useRouter();
  const [annual, setAnnual] = useState(true);
  const [loadingTier, setLoadingTier] = useState<TierId | null>(null);

  const hobbySavings = (TIERS[1].monthly - TIERS[1].annual) * 12;
  const teamSavings = (TIERS[2].monthly - TIERS[2].annual) * 12;
  const savingsByTier: Record<TierId, number> = { free: 0, hobby: hobbySavings, team: teamSavings };

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
        tier.id as "hobby" | "team",
        cycle,
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
        <span className="text-xs font-medium tracking-wide text-brand uppercase">Pricing</span>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
          Simple per-scan-type limits
        </h2>
        <p className="mt-2 text-muted-foreground">No surprise overages, ever.</p>
        <div className="mt-6 flex items-center justify-center gap-3">
          <span className={annual ? "text-muted-foreground" : ""}>Monthly</span>
          <Switch checked={annual} onCheckedChange={setAnnual} aria-label="Toggle annual billing" />
          <span className={annual ? "" : "text-muted-foreground"}>
            Annual
          </span>
        </div>
      </Reveal>

      <div className="mt-10 grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {TIERS.map((tier, i) => {
          const price = annual ? tier.annual : tier.monthly;
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
                    <span className="text-3xl font-semibold">${price}</span>
                    <span className="text-sm text-muted-foreground">/mo</span>
                  </div>
                  {annual && tier.id !== "free" && (
                    <p className="text-xs text-muted-foreground">
                      Billed annually — save ${savingsByTier[tier.id]}/year
                    </p>
                  )}
                </CardHeader>
                <CardContent className="flex flex-col gap-4">
                  <ul className="flex flex-col gap-2 text-sm">
                    {tier.features.map((f) => (
                      <li key={f} className="flex items-start gap-2">
                        <Check className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>
                  <Button
                    className="w-full"
                    variant={tier.popular ? "default" : "outline"}
                    disabled={loadingTier === tier.id}
                    onClick={() => handleCta(tier)}
                  >
                    {loadingTier === tier.id ? "Please wait…" : tier.cta}
                  </Button>
                </CardContent>
              </Card>
            </Reveal>
          );
        })}
      </div>

      <div className="mt-16 overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse text-sm">
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
            <tr>
              <td className="py-3 text-muted-foreground">Compliance report export (PDF)</td>
              {TIERS.map((t) => (
                <td key={t.id} className="py-3 text-center">
                  {t.pdfExport ? <Check className="mx-auto size-4" /> : "—"}
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
    </section>
  );
}
