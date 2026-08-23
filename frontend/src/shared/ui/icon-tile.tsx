import * as React from "react";
import { cn } from "@/shared/lib/utils";
import { Panel } from "./panel";

type Tone = "default" | "brand" | "critical" | "high" | "medium" | "success";

const TONE: Record<Tone, string> = {
  default: "bg-muted text-muted-foreground ring-1 ring-border ring-inset",
  brand: "bg-brand text-brand-foreground",
  critical: "bg-severity-critical-solid text-severity-critical-foreground",
  high: "bg-severity-high text-severity-high-foreground",
  medium: "bg-severity-medium text-severity-medium-foreground",
  success: "bg-brand text-brand-foreground",
};

/**
 * Tabler's `avatar`: a 40px rounded square holding one glyph. It is what
 * gives a row of small stat cards a consistent left edge, and it is
 * decorative in every use here, so the glyph never carries meaning the
 * adjacent text does not.
 */
export function IconTile({
  children,
  tone = "default",
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex size-10 shrink-0 items-center justify-center rounded-md [&_svg]:size-5",
        TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/**
 * Tabler's `card-sm`: icon tile on the left, a bold line and a muted line on
 * the right. Reads at a glance in a four-across row.
 */
export function StatTile({
  icon,
  tone = "default",
  title,
  subtitle,
  action,
  className,
}: {
  icon: React.ReactNode;
  tone?: Tone;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <Panel className={cn("flex-row items-center gap-3 px-4 py-3", className)}>
      <IconTile tone={tone}>{icon}</IconTile>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{title}</div>
        {subtitle ? (
          <div className="truncate text-[13px] leading-5 text-muted-foreground">{subtitle}</div>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </Panel>
  );
}
