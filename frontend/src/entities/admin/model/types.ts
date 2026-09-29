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

export type AdminPayment = {
  id: string;
  tier: string;
  cycle: string;
  seats: number;
  /** Minor units of `currency`: cents for USD, paise for INR. */
  amount_paise: number;
  currency: string;
  status: "created" | "paid" | "failed";
  razorpay_order_id: string | null;
  razorpay_payment_id: string | null;
  created_at: string | null;
  verified_at: string | null;
};

export type AdminWorkspace = {
  org_id: string;
  name: string;
  role: string | null;
  is_owner: boolean;
  /** Owner only. 1 unless the owner's own Team plan is active. */
  seat_limit: number | null;
  /** Owner only. Members plus open invitations. */
  seats_used: number | null;
};

export type AdminUserDetail = {
  user_id: string;
  email: string | null;
  tier: string;
  /** This account's own plan, if still paid for. */
  effective_tier: string;
  /** What is enforced: "team" for a member of an active Team workspace. */
  entitled_tier: string;
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
  /** accounts.seats as bought or granted; in force only while this
   *  account's own Team plan is active. */
  seats: number;
  workspace: AdminWorkspace | null;
  payments: AdminPayment[];
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
