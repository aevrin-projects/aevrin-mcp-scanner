"use client";

import * as React from "react";
import { TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { Panel } from "./panel";
import { Progress } from "./progress";

type Tone = "default" | "critical" | "high" | "medium" | "success";

const TONE_TEXT: Record<Tone, string> = {
  default: "text-foreground",
  critical: "text-severity-critical",
  high: "text-severity-high",
  medium: "text-severity-medium",
  success: "text-brand-text",
};

const TONE_FILL: Record<Tone, string> = {
  default: "bg-foreground/70",
  critical: "bg-severity-critical",
  high: "bg-severity-high",
  medium: "bg-severity-medium",
  success: "bg-brand",
};

/**
 * Tabler's figure block: uppercase label, the number at 24px, an optional
 * qualifier and delta on the same baseline, and a 4px progress rail under it.
 *
 * `delta` is rendered with an arrow as well as a colour so the direction
 * survives for anyone who cannot separate the two greens and reds.
 */
export function Metric({
  label,
  value,
  suffix,
  delta,
  detail,
  progress,
  tone = "default",
  className,
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  suffix?: React.ReactNode;
  delta?: { value: string; direction: "up" | "down"; good?: boolean };
  detail?: React.ReactNode;
  /** 0-1. Renders the rail under the figure when supplied. */
  progress?: number;
  tone?: Tone;
  className?: string;
}) {
  const Arrow = delta?.direction === "down" ? TrendingDown : TrendingUp;
  const deltaGood = delta?.good ?? delta?.direction === "up";

  return (
    <div className={cn("flex flex-col", className)}>
      <div className="subheader">{label}</div>
      <div className="mt-1.5 flex items-baseline gap-2">
        <span
          className={cn(
            "text-2xl leading-8 font-semibold tracking-tight tabular-nums",
            TONE_TEXT[tone],
          )}
        >
          {value}
        </span>
        {suffix ? <span className="text-[13px] text-muted-foreground">{suffix}</span> : null}
        {delta ? (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 text-[13px] leading-4 font-medium",
              deltaGood ? "text-brand-text" : "text-severity-high",
            )}
          >
            {delta.value}
            <Arrow className="size-3.5" aria-hidden="true" />
            <span className="sr-only">{delta.direction === "up" ? "increase" : "decrease"}</span>
          </span>
        ) : null}
      </div>
      {progress !== undefined ? (
        <Progress className="mt-3" value={progress} barClassName={TONE_FILL[tone]} label={String(label)} />
      ) : null}
      {detail ? <p className="mt-2 text-[13px] leading-5 text-muted-foreground">{detail}</p> : null}
    </div>
  );
}

/** A Metric on its own panel, for the stat row at the top of a screen. */
export function MetricCard(props: React.ComponentProps<typeof Metric>) {
  return (
    <Panel className="px-5 py-4">
      <Metric {...props} />
    </Panel>
  );
}
