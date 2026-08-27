import { AlertTriangle, CircleHelp, Clock, ShieldCheck } from "lucide-react";

import type { ListingSecurity } from "../model/types";

/**
 * The scan's status in one line, phrased as what it means rather than as a
 * state name.
 *
 * Each variant says the consequence out loud. "PARTIAL" tells a reader
 * nothing; "Partial coverage — do not treat as clean" tells them what to do
 * with it. This is the component that stands between a half-finished scan and
 * someone reading it as a pass.
 */

export function ScanStatePill({ security }: { security: ListingSecurity }) {
  const config = {
    complete: {
      icon: ShieldCheck,
      className: "border-severity-low/25 bg-severity-low/10 text-severity-low",
      text: security.scannedAt
        ? `Scanned ${formatDate(security.scannedAt)}`
        : "Scanned",
    },
    partial: {
      icon: AlertTriangle,
      className: "border-severity-medium/25 bg-severity-medium/10 text-severity-medium",
      text: "Partial coverage — do not treat as clean",
    },
    outdated: {
      icon: Clock,
      className: "border-severity-medium/25 bg-severity-medium/10 text-severity-medium",
      text: security.latestVersion
        ? `Scan covers ${security.scannedVersion}, current is ${security.latestVersion}`
        : "Scan is older than the current release",
    },
    unscanned: {
      icon: CircleHelp,
      className: "border-border bg-muted text-muted-foreground",
      text: "Not yet scanned",
    },
  }[security.state];

  const Icon = config.icon;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${config.className}`}
    >
      <Icon className="size-3.5 shrink-0" aria-hidden="true" />
      {config.text}
    </span>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return "recently";
  }
}
