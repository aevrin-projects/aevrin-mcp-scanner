export type Tier = "free" | "hobby" | "pro" | "team";

export interface Subscription {
  tier: Tier;
  effective_tier: Tier;
  paid_until: string | null;
}

export interface Payment {
  id: string;
  // "autofix_addon" is a historical tier: it is no longer sold, but rows
  // for it are still in billing history and have to render.
  tier: "hobby" | "pro" | "team" | "autofix_addon";
  cycle: "monthly" | "annual";
  seats: number;
  byok: boolean;
  amount_paise: number;
  currency: string;
  status: "created" | "paid" | "failed";
  created_at: string;
  verified_at: string | null;
}
