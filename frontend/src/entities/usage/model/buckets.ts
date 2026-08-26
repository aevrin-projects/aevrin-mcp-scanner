import { Bot, LayoutDashboard, ShieldCheck, TerminalSquare } from "lucide-react";
import type { UsageBucket } from "@/entities/usage";

/**
 * Shared identity for every usage bucket, label, description, icon, and
 * hue. Kept in one place because the compact meters on the dashboard and the
 * full breakdown on /usage show the same things; if "CLI scans" is teal
 * in one and amber in the other, the color stops being a shortcut and starts
 * being noise.
 *
 * The hue is *identity only*. Anything showing consumption overrides it with
 * a state color once a bucket nears its limit; see `usageFillColor`.
 */
export const USAGE_BUCKETS: Record<
  UsageBucket,
  { label: string; description: string; color: string; icon: typeof TerminalSquare }
> = {
  dashboard: {
    label: "Dashboard scans",
    description: "Scans started from the authenticated web workspace.",
    color: "var(--chart-4)",
    icon: LayoutDashboard,
  },
  cli: {
    label: "CLI scans",
    description: "Authenticated terminal scans counted by the CLI quota bucket.",
    color: "var(--chart-3)",
    icon: TerminalSquare,
  },
  hook: {
    label: "Hook auto-scans",
    description: "Scans requested by the Claude Code pre-install workflow.",
    color: "var(--chart-1)",
    icon: ShieldCheck,
  },
  agent: {
    label: "Agent posture scans",
    // One per `aevrin agent scan --upload`, however many agents it found.
    description: "One per posture upload, however many agents that upload reported.",
    color: "var(--chart-2)",
    icon: Bot,
  },
};

/** An upgrade CTA appears once any meter crosses this fraction of its limit. */
export const UPGRADE_THRESHOLD = 0.8;

/** State beats identity: at the limit a meter is red, near it amber,
 *  otherwise the bucket's own hue. */
export function usageFillColor(bucket: UsageBucket, ratio: number): string {
  if (ratio >= 1) return "var(--severity-critical)";
  if (ratio >= UPGRADE_THRESHOLD) return "var(--severity-medium)";
  return USAGE_BUCKETS[bucket].color;
}
