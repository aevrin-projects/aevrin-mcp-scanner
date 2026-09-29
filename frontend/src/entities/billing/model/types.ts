export type Tier = "free" | "hobby" | "pro" | "team";

export interface Subscription {
  /** What this account bought, stored as-is (may have lapsed). */
  tier: Tier;
  /** What the server enforces: "team" for a member of a workspace whose
   *  owner's Team plan is active, even when the member bought nothing. */
  effective_tier: Tier;
  /** This account's own purchase, if it is still paid for. */
  own_effective_tier: Tier;
  paid_until: string | null;
  /** Seats bought or granted on this account; in force only while
   *  `own_effective_tier` is "team". */
  seats: number;
  /** Members plus open invitations, when this account owns a workspace. */
  seats_used: number | null;
}

export interface Payment {
  id: string;
  // "autofix_addon" and "byok_addon" are historical: neither is sold any
  // more, but rows for them are still in billing history and have to render.
  tier: "hobby" | "pro" | "team" | "autofix_addon" | "byok_addon";
  cycle: "monthly" | "annual";
  seats: number;
  amount_paise: number;
  currency: string;
  status: "created" | "paid" | "failed";
  created_at: string;
  verified_at: string | null;
}
