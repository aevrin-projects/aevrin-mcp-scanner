import * as React from "react";
import { cn } from "@/shared/lib/utils";

/** Tabler's `progress progress-sm`: an 8px rail on the muted surface. */
export function Progress({
  value,
  label,
  barClassName,
  barStyle,
  className,
}: {
  /** 0-1, clamped. */
  value: number;
  /** Accessible name; the rail is a progressbar, not decoration. */
  label: string;
  barClassName?: string;
  barStyle?: React.CSSProperties;
  className?: string;
}) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("h-2 w-full overflow-hidden rounded-full bg-muted", className)}
    >
      <div
        className={cn("h-full rounded-full transition-[width] duration-500", barClassName ?? "bg-brand")}
        style={{ width: `${pct}%`, ...barStyle }}
      />
    </div>
  );
}
