import { GitPullRequest, LayoutDashboard, ShieldCheck, TerminalSquare } from "lucide-react";
import type { UsageBucket } from "@/lib/types";

/**
 * Shared identity for the four usage buckets — label, description, icon, and
 * hue. Kept in one place because the compact meters on the dashboard and the
 * full breakdown on /usage show the same four things; if "CLI scans" is teal
 * in one and amber in the other, the color stops being a shortcut and starts
 * being noise.
 *
 * The hue is *identity only*. Anything showing consumption overrides it with
 * a state color once a bucket nears its limit — see `usageFillColor`.
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
  auto_fix: {
    label: "Auto-fix PRs",
    description: "Fix It pull requests opened this period, Pro and Team only.",
    color: "var(--brand)",
    icon: GitPullRequest,
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
