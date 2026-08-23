import { publicRequest, request } from "@/shared/api";
import type { Payment, Subscription } from "../model/types";

type CheckoutOrder = {
  order_id: string;
  amount_paise: number;
  currency: string;
  razorpay_key_id: string;
};

export const billingApi = {
  getSubscription: () => request<Subscription>("/billing/subscription"),
  getPayments: () => request<Payment[]>("/billing/payments"),
  createCheckout: (
    tier: "hobby" | "pro" | "team",
    cycle: "monthly" | "annual",
    // `currency` is a preference, not a decision: the API re-derives it and
    // only honours this when it does not lower the price.
    options?: { seats?: number; byok?: boolean; currency?: string | null },
  ) =>
    request<CheckoutOrder>(
      `/billing/checkout${options?.currency ? `?currency=${encodeURIComponent(options.currency)}` : ""}`,
      {
        method: "POST",
        body: JSON.stringify({ tier, cycle, seats: options?.seats ?? 1, byok: options?.byok ?? false }),
      },
    ),
  /** Public: the pricing page has to render for signed-out visitors, so this
   *  deliberately skips the auth header rather than throwing. */
  getPricing: (currency?: string | null) =>
    publicRequest<{
      currency: string;
      tiers: Record<string, number>;
      byok_addon_per_month: number;
      autofix_addon: number;
    }>(`/billing/pricing${currency ? `?currency=${encodeURIComponent(currency)}` : ""}`),
  verifyPayment: (razorpay_order_id: string, razorpay_payment_id: string, razorpay_signature: string) =>
    request<{ status: string; tier: string; paid_until: string }>("/billing/verify", {
      method: "POST",
      body: JSON.stringify({ razorpay_order_id, razorpay_payment_id, razorpay_signature }),
    }),
  createByokAddonCheckout: () =>
    request<CheckoutOrder>("/billing/addon/byok/checkout", { method: "POST" }),
  createAutofixAddonCheckout: () =>
    request<CheckoutOrder>("/billing/addon/autofix/checkout", { method: "POST" }),
  getByokStatus: () =>
    request<{ enabled: boolean; provider: "anthropic" | "google" | null; has_key: boolean }>("/billing/byok"),
  setByokKey: (provider: "anthropic" | "google", api_key: string) =>
    request<{ enabled: boolean; provider: string | null; has_key: boolean }>("/billing/byok", {
      method: "POST",
      body: JSON.stringify({ provider, api_key }),
    }),
  clearByokKey: () => request<{ status: string }>("/billing/byok", { method: "DELETE" }),
};
