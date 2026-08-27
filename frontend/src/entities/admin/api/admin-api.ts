import { request } from "@/shared/api";
import type { AdminAuditEntry, AdminLoginAttempt, AdminUserDetail, AdminUserPage } from "../model/types";

export const adminApi = {
  getSession: () =>
    request<{ is_admin: boolean; totp_enrolled: boolean; session_fresh: boolean; email: string | null }>(
      "/admin/session",
    ),
  enrolTotp: () => request<{ secret: string; provisioning_uri: string }>("/admin/totp/enrol", { method: "POST" }),
  verifyTotp: (code: string) =>
    request<{ ok: boolean }>("/admin/totp/verify", { method: "POST", body: JSON.stringify({ code }) }),

  listUsers: (params: { q?: string; status?: string; page?: number }) => {
    const search = new URLSearchParams();
    if (params.q) search.set("q", params.q);
    if (params.status) search.set("status", params.status);
    search.set("page", String(params.page ?? 1));
    return request<AdminUserPage>(`/admin/users?${search.toString()}`);
  },
  getUserDetail: (id: string) => request<AdminUserDetail>(`/admin/users/${id}`),
  setStatus: (id: string, body: { status: string; reason: string; totp_code: string }) =>
    request<{ status: string }>(`/admin/users/${id}/status`, { method: "POST", body: JSON.stringify(body) }),
  setPlan: (id: string, body: { tier: string; reason: string; months: number; totp_code: string }) =>
    request<{ tier: string }>(`/admin/users/${id}/plan`, { method: "POST", body: JSON.stringify(body) }),
  deleteUser: (id: string, body: { reason: string; totp_code: string }) =>
    request<{
      email: string;
      scans_deleted: number;
      findings_deleted: number;
      payments_deleted: number;
    }>(`/admin/users/${id}`, { method: "DELETE", body: JSON.stringify(body) }),
  /** Seats an account's workspace may fill. The same number a Team purchase
   *  writes, so granting and buying move one value, not two. */
  setSeats: (id: string, body: { seats: number; reason: string }) =>
    request<{ seats: number }>(`/admin/users/${id}/seats`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  setOverride: (
    id: string,
    body: {
      bucket: string;
      limit_value?: number | null;
      unlimited?: boolean;
      expires_at?: string | null;
      reason: string;
    },
  ) => request<Record<string, unknown>>(`/admin/users/${id}/overrides`, { method: "POST", body: JSON.stringify(body) }),
  clearOverride: (id: string, bucket: string) =>
    request<{ bucket: string }>(`/admin/users/${id}/overrides/${bucket}`, { method: "DELETE" }),
  resetUsage: (id: string, body: { bucket: string; reason: string }) =>
    request<Record<string, unknown>>(`/admin/users/${id}/reset-usage`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  sendPasswordReset: (id: string, reason: string) =>
    request<{ sent: boolean; email: string }>(`/admin/users/${id}/password-reset`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  getAnalytics: (days: number) => request<Record<string, unknown>>(`/admin/analytics?days=${days}`),
  getAccountUsage: () => request<Array<Record<string, unknown>>>("/admin/account-usage"),
  getAudit: (params: { target?: string; action?: string; limit?: number }) => {
    const search = new URLSearchParams();
    if (params.target) search.set("target", params.target);
    if (params.action) search.set("action", params.action);
    search.set("limit", String(params.limit ?? 100));
    return request<AdminAuditEntry[]>(`/admin/audit?${search.toString()}`);
  },
  getLoginAttempts: () => request<AdminLoginAttempt[]>("/admin/login-attempts"),
};

/**
 * Marketplace administration.
 *
 * Mounted under the same `/admin` prefix as everything else here, so it goes
 * through the same admin-session and TOTP checks. There is deliberately no
 * method below that writes a grade, a score, or a coverage flag: those come
 * from scans, and an admin who could type a better letter could make an unsafe
 * server look safe.
 */
export const marketplaceAdminApi = {
  summary: () =>
    request<{
      total: number;
      scanned: number;
      unscanned: number;
      stale_scans: number;
      partial_coverage: number;
      grades: Record<string, number>;
      statuses: Record<string, number>;
      open_reports: number;
      pending_submissions: number;
    }>("/admin/marketplace/summary"),

  list: (params: {
    status?: string;
    grade?: string;
    unscanned?: boolean;
    q?: string;
    limit?: number;
    offset?: number;
  }) => {
    const search = new URLSearchParams();
    if (params.status) search.set("status", params.status);
    if (params.grade) search.set("grade", params.grade);
    if (params.unscanned) search.set("unscanned", "true");
    if (params.q) search.set("q", params.q);
    if (params.limit) search.set("limit", String(params.limit));
    if (params.offset) search.set("offset", String(params.offset));
    return request<Record<string, unknown>[]>(`/admin/marketplace/mcp?${search.toString()}`);
  },

  create: (body: { source_url: string; visibility?: string; org_id?: string | null }) =>
    request<Record<string, unknown>>("/admin/marketplace/mcp", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  patch: (id: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/admin/marketplace/mcp/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  setStatus: (id: string, status: string, reason?: string) =>
    request<Record<string, unknown>>(`/admin/marketplace/mcp/${id}/status`, {
      method: "POST",
      body: JSON.stringify({ status, reason: reason ?? null }),
    }),

  scan: (id: string, force: boolean) =>
    request<{ reused: boolean; scan_id: string; reason: string }>(
      `/admin/marketplace/mcp/${id}/scan`,
      { method: "POST", body: JSON.stringify({ force, version_id: null }) },
    ),

  submissions: (status = "review") =>
    request<Record<string, unknown>[]>(`/admin/marketplace/submissions?status=${status}`),

  decideSubmission: (id: string, decision: "approved" | "rejected", reason?: string) =>
    request<Record<string, unknown>>(`/admin/marketplace/submissions/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, reason: reason ?? null }),
    }),

  reports: (status = "open") =>
    request<Record<string, unknown>[]>(`/admin/marketplace/reports?status=${status}`),

  resolveReport: (id: string, status: string, note?: string) =>
    request<Record<string, unknown>>(`/admin/marketplace/reports/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ status, note: note ?? null }),
    }),
};
