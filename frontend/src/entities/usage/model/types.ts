import type { ScanSource, ScanStatus, TargetType } from "@/entities/scan";

export type UsageBucket = "cli" | "hook" | "dashboard" | "auto_fix";

export interface BucketUsage {
  bucket: UsageBucket;
  used: number;
  /** null = unlimited (Team). */
  limit: number | null;
  resets_at: string;
}

export interface AccountUsage {
  tier: "free" | "hobby" | "team";
  paid_until: string | null;
  buckets: BucketUsage[];
  activity: UsageActivity[];
}

export interface UsageActivity {
  id: string;
  source: ScanSource;
  target_type: TargetType;
  target: string;
  status: ScanStatus;
  score: number | null;
  created_at: string;
  completed_at: string | null;
}
