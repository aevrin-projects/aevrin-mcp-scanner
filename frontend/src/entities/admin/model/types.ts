/** Mirrors the response models in backend/api/src/aevrin_api/routes/admin.py.
 *  Nothing here ever carries a credential: the API returns masked or derived
 *  values only. */

export type AdminUserRow = {
  user_id: string;
  email: string | null;
  tier: string;
  effective_tier: string;
  status: "active" | "disabled" | "blocked";
  flagged: boolean;
  paid_until: string | null;
  created_at: string | null;
  last_scan_at: string | null;
  scans_this_period: number;
};

export type AdminUserPage = {
  rows: AdminUserRow[];
  total: number;
  page: number;
  page_size: number;
};

export type AdminUsageBucket = {
  bucket: string;
  used: number;
  limit: number | null;
  resets_at: string;
};

export type AdminQuotaOverride = {
  bucket: string;
  limit_value: number | null;
  expires_at: string | null;
  reason: string | null;
  created_at: string;
};

export type AdminUserDetail = {
  user_id: string;
  email: string | null;
  tier: string;
  effective_tier: string;
  status: "active" | "disabled" | "blocked";
  status_reason: string | null;
  flagged: boolean;
  paid_until: string | null;
  created_at: string | null;
  /** False for OAuth-only accounts, which have no password to reset. */
  has_password: boolean;
  auth_providers: string[];
  usage: AdminUsageBucket[];
  overrides: AdminQuotaOverride[];
  recent_scans: Array<Record<string, unknown>>;
  api_key_count: number;
  github_connected: boolean;
  /** People this account's workspace may hold, owner included. */
  seats: number;
};

export type AdminAuditEntry = {
  id: number;
  actor_user_id: string;
  actor_email: string | null;
  action: string;
  target_user_id: string | null;
  target_email: string | null;
  target_resource: string | null;
  reason: string | null;
  metadata: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
};

export type AdminLoginAttempt = {
  id: number;
  email: string | null;
  succeeded: boolean;
  failure_reason: string | null;
  ip_address: string | null;
  created_at: string;
};
