"use client";

import * as React from "react";
import { AlertTriangle, ShieldCheck } from "lucide-react";
import { cn } from "@/shared/lib/utils";

/**
 * Tabler's `empty` block: centred glyph, one-line title, a short explanation
 * and a single action. Centred rather than left-aligned because an empty
 * region has no other content to align to, and an off-centre block in an
 * otherwise blank panel reads as a rendering fault.
 */
export function EmptyState({
  title,
  body,
  icon,
  variant = "neutral",
  action,
  className,
}: {
  title: React.ReactNode;
  body?: React.ReactNode;
  icon?: React.ReactNode;
  variant?: "neutral" | "attention";
  action?: React.ReactNode;
  className?: string;
}) {
  const Fallback = variant === "attention" ? AlertTriangle : ShieldCheck;

  return (
    <div className={cn("flex flex-col items-center px-6 py-12 text-center", className)}>
      <span
        aria-hidden="true"
        className={cn(
          "mb-4 inline-flex size-12 items-center justify-center rounded-full [&_svg]:size-6",
          variant === "attention"
            ? "bg-severity-high/10 text-severity-high"
            : "bg-muted text-muted-foreground",
        )}
      >
        {icon ?? <Fallback />}
      </span>
      <h3 className="text-base font-medium">{title}</h3>
      {body ? (
        <p className="mt-1.5 max-w-md text-[13px] leading-5 text-muted-foreground">{body}</p>
      ) : null}
      {action ? <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div> : null}
    </div>
  );
}
