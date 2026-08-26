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
