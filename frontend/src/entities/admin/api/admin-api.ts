import { request } from "@/shared/api";
import type {
  AdminAuditEntry,
  AdminLoginAttempt,
  AdminUserDetail,
  AdminUserPage,
  BulkPublishResult,
} from "../model/types";

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
   *  writes, so granting and buying move one value, not two. Gated on the
   *  authentication code like a plan change, and in force only while the
   *  account's own Team plan is active. */
  setSeats: (id: string, body: { seats: number; reason: string; totp_code: string }) =>
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
  getAudit: (params: { target?: string; action?: string; since?: string; limit?: number }) => {
    const search = new URLSearchParams();
    if (params.target) search.set("target", params.target);
    if (params.action) search.set("action", params.action);
    if (params.since) search.set("since", params.since);
    search.set("limit", String(params.limit ?? 100));
    return request<AdminAuditEntry[]>(`/admin/audit?${search.toString()}`);
  },
  getLoginAttempts: () => request<AdminLoginAttempt[]>("/admin/login-attempts"),
};

/**
 * Registry administration: the only way anything is added to, changed in,
 * published from or removed from the Aevrin Registry.
 *
 * Mounted under the same `/admin` prefix as everything else here, so it goes
 * through the same admin-session and TOTP checks. `patch` never changes
 * status: publishing goes through `setStatus`, which runs the publish gate.
 */
export const marketplaceAdminApi = {
  summary: () =>
    request<{
      total: number;
      statuses: Record<string, number>;
      types: Record<string, number>;
      open_reports: number;
      pending_submissions: number;
    }>("/admin/marketplace/summary"),

  list: (params: {
    status?: string;
    q?: string;
    type?: string;
    limit?: number;
    offset?: number;
  }) => {
    const search = new URLSearchParams();
    if (params.status) search.set("status", params.status);
    if (params.type) search.set("type", params.type);
    if (params.q) search.set("q", params.q);
    if (params.limit) search.set("limit", String(params.limit));
    if (params.offset) search.set("offset", String(params.offset));
    return request<Record<string, unknown>[]>(`/admin/marketplace/mcp?${search.toString()}`);
  },

  /** Always creates a draft. From a URL (derived like a suggestion), or by
   *  hand with a title - a prompt or a skill often has no repository. */
  create: (body: {
    item_type: string;
    source_url?: string | null;
    title?: string | null;
    description?: string | null;
    visibility?: string;
    org_id?: string | null;
  }) =>
    request<Record<string, unknown>>("/admin/marketplace/mcp", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** One item in any state, with `validation_issues`: every reason it cannot
   *  be published yet. The editor's preview reads this. */
  get: (id: string) => request<Record<string, unknown>>(`/admin/marketplace/mcp/${id}`),

  /** Removes the registry entry only - never the repository.
   *  The slug must be typed back. */
  remove: (id: string, confirmSlug: string) =>
    request<{ deleted: boolean; slug: string }>(`/admin/marketplace/mcp/${id}`, {
      method: "DELETE",
      body: JSON.stringify({ confirm_slug: confirmSlug }),
    }),

  refreshMetadata: (id: string) =>
    request<Record<string, unknown>>(`/admin/marketplace/mcp/${id}/refresh-metadata`, {
      method: "POST",
    }),

  setLinks: (id: string, links: { related_id: string; relation: "uses" | "related" }[]) =>
    request<{ related_id: string; relation: string }[]>(`/admin/marketplace/mcp/${id}/links`, {
      method: "PUT",
      body: JSON.stringify({ links }),
    }),

  categories: () =>
    request<{ slug: string; name: string; description: string | null; sort_order: number }[]>(
      "/admin/marketplace/categories",
    ),

  saveCategory: (body: { slug: string; name: string; description?: string | null; sort_order?: number }) =>
    request<Record<string, unknown>>("/admin/marketplace/categories", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  deleteCategory: (slug: string) =>
    request<{ deleted: boolean }>(`/admin/marketplace/categories/${encodeURIComponent(slug)}`, {
      method: "DELETE",
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

  /** What "Apply popularity bar" would publish, and why the rest would
   *  stay drafts. Writes nothing. */
  bulkPublishPreview: () => request<BulkPublishResult>("/admin/marketplace/bulk-publish"),

  /** Publishes the qualifying drafts, at most `criteria.max_per_call` per
   *  call; the server recomputes the set rather than trusting the preview.
   *  `remaining` > 0 means call again. */
  bulkPublish: () =>
    request<BulkPublishResult>("/admin/marketplace/bulk-publish", { method: "POST" }),

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
