"use client";

import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL!;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function authHeaders(): Promise<Record<string, string>> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) {
    throw new ApiError(401, "Not signed in");
  }
  return { Authorization: `Bearer ${session.access_token}` };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = await authHeaders();
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { ...headers, "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Could not reach the Aevrin API. Check your connection and try again.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // non-JSON error body, fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  createScan: (target_type: string, target: string) =>
    request<import("@/lib/types").Scan>("/scans", {
      method: "POST",
      body: JSON.stringify({ target_type, target }),
    }),
  listScans: () => request<import("@/lib/types").Scan[]>("/scans"),
  deleteScan: (id: string) => request<void>(`/scans/${id}`, { method: "DELETE" }),
  clearScanHistory: () => request<void>("/scans", { method: "DELETE" }),
  getScan: (id: string) => request<import("@/lib/types").Scan>(`/scans/${id}`),
  getScanStages: (id: string) =>
    request<import("@/lib/types").ScanStage[]>(`/scans/${id}/stages`),
  getScanFindings: (id: string) =>
    request<import("@/lib/types").Finding[]>(`/scans/${id}/findings`),
  getFinding: (id: string) => request<import("@/lib/types").Finding>(`/findings/${id}`),
  triageFinding: (id: string, triage_status: string, reason?: string) =>
    request<import("@/lib/types").Finding>(`/findings/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ triage_status, reason }),
    }),
  exportReport: (id: string) => request<{ url: string }>(`/scans/${id}/export`),
  listApiKeys: () => request<import("@/lib/types").ApiKey[]>("/api-keys"),
  createApiKey: (name: string) =>
    request<{ id: number; name: string; plaintext_key: string }>("/api-keys", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  revokeApiKey: (id: number) => request<void>(`/api-keys/${id}`, { method: "DELETE" }),
  getUsage: () => request<import("@/lib/types").AccountUsage>("/account/usage"),
  approveDevice: (userCode: string, fingerprint: string | null) =>
    request<{ status: string }>(`/device/${userCode}/approve`, {
      method: "POST",
      body: JSON.stringify({ user_code: userCode, fingerprint }),
    }),
  getSubscription: () => request<import("@/lib/types").Subscription>("/billing/subscription"),
  getPayments: () => request<import("@/lib/types").Payment[]>("/billing/payments"),
  createCheckout: (
    tier: "hobby" | "pro" | "team",
    cycle: "monthly" | "annual",
    options?: { seats?: number; byok?: boolean },
  ) =>
    request<{ order_id: string; amount_paise: number; currency: string; razorpay_key_id: string }>(
      "/billing/checkout",
      {
        method: "POST",
        body: JSON.stringify({ tier, cycle, seats: options?.seats ?? 1, byok: options?.byok ?? false }),
      },
    ),
  verifyPayment: (razorpay_order_id: string, razorpay_payment_id: string, razorpay_signature: string) =>
    request<{ status: string; tier: string; paid_until: string }>("/billing/verify", {
      method: "POST",
      body: JSON.stringify({ razorpay_order_id, razorpay_payment_id, razorpay_signature }),
    }),
  createAutofixAddonCheckout: () =>
    request<{ order_id: string; amount_paise: number; currency: string; razorpay_key_id: string }>(
      "/billing/addon/autofix/checkout",
      { method: "POST" },
    ),
  getGithubStatus: () => request<{ connected: boolean; account_login: string | null }>("/github/status"),
  getGithubInstallUrl: () => request<{ url: string }>("/github/install-url"),
  fixFinding: (findingId: string) =>
    request<{ status: string; pr_url: string | null; failure_reason: string | null; install_url: string | null }>(
      `/findings/${findingId}/fix`,
      { method: "POST" },
    ),
  getByokStatus: () =>
    request<{ enabled: boolean; provider: "anthropic" | "google" | null; has_key: boolean }>("/billing/byok"),
  setByokKey: (provider: "anthropic" | "google", api_key: string) =>
    request<{ enabled: boolean; provider: string | null; has_key: boolean }>("/billing/byok", {
      method: "POST",
      body: JSON.stringify({ provider, api_key }),
    }),
  clearByokKey: () => request<{ status: string }>("/billing/byok", { method: "DELETE" }),
};

// GET /device/{code} doesn't require auth (the approval page needs to show
// what's pending before the person is necessarily logged in) — plain fetch,
// not the authHeaders()-wrapped `request` helper above.
export async function getDeviceCodeInfo(userCode: string): Promise<{ client_kind: string; status: string }> {
  const res = await fetch(`${API_URL}/device/${userCode}`);
  if (!res.ok) {
    throw new ApiError(res.status, res.status === 404 ? "This code is invalid or has expired." : res.statusText);
  }
  return res.json();
}
