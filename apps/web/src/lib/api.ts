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

/** Same error handling as `request`, without requiring a session.
 *  `authHeaders` throws when signed out, which is right for account
 *  endpoints and wrong for anything a visitor can see. */
async function publicRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Could not reach the Aevrin API. Check your connection and try again.");
  }
  if (!res.ok) {
    throw new ApiError(res.status, res.statusText);
  }
  return (await res.json()) as T;
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
    // `currency` is a preference, not a decision: the API re-derives it and
    // only honours this when it does not lower the price.
    options?: { seats?: number; byok?: boolean; currency?: string | null },
  ) =>
    request<{ order_id: string; amount_paise: number; currency: string; razorpay_key_id: string }>(
      `/billing/checkout${options?.currency ? `?currency=${encodeURIComponent(options.currency)}` : ""}`,
      {
        method: "POST",
        body: JSON.stringify({ tier, cycle, seats: options?.seats ?? 1, byok: options?.byok ?? false }),
      },
    ),
  /** Public: the pricing page has to render for signed-out visitors, so
   *  this deliberately skips the auth header rather than throwing. */
  getPricing: (currency?: string | null) =>
    publicRequest<{ currency: string; tiers: Record<string, number>; byok_addon_per_month: number; autofix_addon: number }>(
      `/billing/pricing${currency ? `?currency=${encodeURIComponent(currency)}` : ""}`,
    ),
  verifyPayment: (razorpay_order_id: string, razorpay_payment_id: string, razorpay_signature: string) =>
    request<{ status: string; tier: string; paid_until: string }>("/billing/verify", {
      method: "POST",
      body: JSON.stringify({ razorpay_order_id, razorpay_payment_id, razorpay_signature }),
    }),
  createByokAddonCheckout: () =>
    request<{ order_id: string; amount_paise: number; currency: string; razorpay_key_id: string }>(
      "/billing/addon/byok/checkout",
      { method: "POST" },
    ),
  createAutofixAddonCheckout: () =>
    request<{ order_id: string; amount_paise: number; currency: string; razorpay_key_id: string }>(
      "/billing/addon/autofix/checkout",
      { method: "POST" },
    ),
  getGithubStatus: () => request<{ connected: boolean; account_login: string | null }>("/github/status"),
  getGithubInstallUrl: () => request<{ url: string }>("/github/install-url"),
  // labels=false skips the per-repo MCP heuristic. The picker wants the
  // labels; the Fix It access check only needs the names, and shouldn't wait
  // on ~180 GitHub calls to decide whether to enable a button.
  getGithubRepos: (labels = true) =>
    request<import("@/lib/types").GithubReposResponse>(`/github/repos?labels=${labels}`),
  // --- admin panel -------------------------------------------------------
  adminSession: () =>
    request<{ is_admin: boolean; totp_enrolled: boolean; session_fresh: boolean; email: string | null }>(
      "/admin/session",
    ),
  adminTotpEnrol: () =>
    request<{ secret: string; provisioning_uri: string }>("/admin/totp/enrol", { method: "POST" }),
  adminTotpVerify: (code: string) =>
    request<{ ok: boolean }>("/admin/totp/verify", { method: "POST", body: JSON.stringify({ code }) }),
  adminListUsers: (params: { q?: string; status?: string; page?: number }) => {
    const search = new URLSearchParams();
    if (params.q) search.set("q", params.q);
    if (params.status) search.set("status", params.status);
    search.set("page", String(params.page ?? 1));
    return request<import("@/lib/types").AdminUserPage>(`/admin/users?${search.toString()}`);
  },
  adminUserDetail: (id: string) => request<import("@/lib/types").AdminUserDetail>(`/admin/users/${id}`),
  adminSetStatus: (id: string, body: { status: string; reason: string; totp_code: string }) =>
    request<{ status: string }>(`/admin/users/${id}/status`, { method: "POST", body: JSON.stringify(body) }),
  adminSetPlan: (id: string, body: { tier: string; reason: string; months: number; totp_code: string }) =>
    request<{ tier: string }>(`/admin/users/${id}/plan`, { method: "POST", body: JSON.stringify(body) }),
  adminGrantAddon: (
    id: string,
    body: { addon: string; quantity?: number; bucket?: string; expires_at?: string | null; reason: string },
  ) => request<Record<string, unknown>>(`/admin/users/${id}/addons`, { method: "POST", body: JSON.stringify(body) }),
  adminSetOverride: (
    id: string,
    body: { bucket: string; limit_value?: number | null; unlimited?: boolean; expires_at?: string | null; reason: string },
  ) => request<Record<string, unknown>>(`/admin/users/${id}/overrides`, { method: "POST", body: JSON.stringify(body) }),
  adminClearOverride: (id: string, bucket: string) =>
    request<{ bucket: string }>(`/admin/users/${id}/overrides/${bucket}`, { method: "DELETE" }),
  adminResetUsage: (id: string, body: { bucket: string; reason: string }) =>
    request<Record<string, unknown>>(`/admin/users/${id}/reset-usage`, { method: "POST", body: JSON.stringify(body) }),
  adminPasswordReset: (id: string, reason: string) =>
    request<{ sent: boolean; email: string }>(`/admin/users/${id}/password-reset`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  adminAnalytics: (days: number) =>
    request<Record<string, unknown>>(`/admin/analytics?days=${days}`),
  adminAccountUsage: () => request<Array<Record<string, unknown>>>("/admin/account-usage"),
  adminAudit: (params: { target?: string; action?: string; limit?: number }) => {
    const search = new URLSearchParams();
    if (params.target) search.set("target", params.target);
    if (params.action) search.set("action", params.action);
    search.set("limit", String(params.limit ?? 100));
    return request<import("@/lib/types").AdminAuditEntry[]>(`/admin/audit?${search.toString()}`);
  },
  adminLoginAttempts: () => request<import("@/lib/types").AdminLoginAttempt[]>("/admin/login-attempts"),

  scanDiff: (scanId: string) => request<import("@/lib/types").ScanDiff>(`/scans/${scanId}/diff`),
  cancelScanFix: (scanId: string) =>
    request<{ cancelled: boolean; released: number }>(`/scans/${scanId}/fix/cancel`, { method: "POST" }),
  fixScan: (scanId: string) =>
    request<import("@/lib/types").BulkFixResponse>(`/scans/${scanId}/fix`, { method: "POST" }),
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
