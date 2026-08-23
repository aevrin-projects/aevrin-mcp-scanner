"use client";

import type { UsageBucket } from "@/entities/usage";
import { USAGE_BUCKETS } from "@/entities/usage";

/**
 * Isometric usage columns. Each bucket is drawn as a 3D block on a shared
 * plinth: a lit top face, a bright front face, and a darker right face, with
 * a translucent "ghost" block above it showing the unused remainder of the
 * limit. The depth is doing real work; it separates *used* from *headroom*
 * far more legibly than two shades of a flat bar.
 *
 * Pure CSS transforms, no library and no canvas. The whole figure is
 * `aria-hidden` and every number in it is repeated as text in the legend
 * beneath, so nothing is conveyed by the drawing alone.
 */

const DEPTH = 14; // px of projected depth, the right/top face offset.
const MAX_HEIGHT = 150; // px for a full bucket.

export type Usage3DBar = {
  bucket: UsageBucket;
  used: number;
  limit: number | null;
};

export function Usage3DChart({ bars }: { bars: Usage3DBar[] }) {
  // Unlimited buckets have no ceiling to draw, so the scale falls back to the
  // largest observed value rather than pretending a limit exists.
  const scaleMax = Math.max(...bars.map((bar) => bar.limit ?? bar.used), 1);

  return (
    <div className="@container">
      <div
        aria-hidden="true"
        className="relative flex items-end justify-center gap-8 overflow-x-auto px-4 pt-8 pb-2 @md:gap-12"
        style={{ minHeight: MAX_HEIGHT + DEPTH + 72 }}
      >
        {bars.map((bar, index) => {
          const meta = USAGE_BUCKETS[bar.bucket];
          const ceiling = bar.limit ?? Math.max(bar.used, 1);
          const usedHeight = Math.round((bar.used / scaleMax) * MAX_HEIGHT);
          const totalHeight = Math.round((ceiling / scaleMax) * MAX_HEIGHT);
          const ghostHeight = Math.max(totalHeight - usedHeight, 0);

          return (
            <div key={bar.bucket} className="flex shrink-0 flex-col items-center">
              <div className="flex flex-col justify-end" style={{ height: MAX_HEIGHT + DEPTH }}>
                {/* Headroom: the same block in outline, so "how much is left"
                    is a shape you can compare across buckets at a glance. */}
                {ghostHeight > 2 ? (
                  <IsoBlock height={ghostHeight} color={meta.color} ghost delay={index * 90} />
                ) : null}
                {/* Used. A zero-usage bucket still draws a sliver so the
                    column reads as "nothing yet", not "missing". */}
                <IsoBlock
                  height={Math.max(usedHeight, 3)}
                  color={meta.color}
                  delay={index * 90 + 40}
                />
              </div>

              {/* Ground plane, so the blocks sit on something. */}
              <div
                className="mt-px"
                style={{
                  width: 56 + DEPTH,
                  height: 1,
                  background: `linear-gradient(90deg, transparent, color-mix(in oklab, ${meta.color} 45%, transparent), transparent)`,
                }}
              />

              <p className="mt-4 text-center text-[11px] tabular-nums text-muted-foreground">
                <span className="font-medium text-foreground">{bar.used}</span>
                {bar.limit === null ? "" : ` / ${bar.limit}`}
              </p>
            </div>
          );
        })}
      </div>

      <ul className="mt-2 flex flex-wrap gap-x-8 gap-y-3 border-t border-border pt-4">
        {bars.map((bar) => {
          const meta = USAGE_BUCKETS[bar.bucket];
          const Icon = meta.icon;
          return (
            <li key={bar.bucket} className="flex items-center gap-2.5">
              <span
                className="flex size-7 shrink-0 items-center justify-center rounded-lg border"
                style={{
                  borderColor: `color-mix(in oklab, ${meta.color} 30%, transparent)`,
                  background: `color-mix(in oklab, ${meta.color} 12%, transparent)`,
                }}
              >
                <Icon aria-hidden="true" className="size-3.5" style={{ color: meta.color }} />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-[12.5px] text-foreground">{meta.label}</span>
                <span className="block text-[11px] tabular-nums text-muted-foreground">
                  {bar.limit === null
                    ? `${bar.used} used · usage-based`
                    : `${bar.used} of ${bar.limit} used`}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** One extruded block: front face, top face, right face. */
function IsoBlock({
  height,
  color,
  ghost = false,
  delay,
}: {
  height: number;
  color: string;
  ghost?: boolean;
  delay: number;
}) {
  const front = ghost
    ? `color-mix(in oklab, ${color} 10%, transparent)`
    : `color-mix(in oklab, ${color} 88%, black)`;
  const top = ghost
    ? `color-mix(in oklab, ${color} 18%, transparent)`
    : `color-mix(in oklab, ${color} 100%, white 18%)`;
  const side = ghost
    ? `color-mix(in oklab, ${color} 6%, transparent)`
    : `color-mix(in oklab, ${color} 62%, black)`;
  const edge = `color-mix(in oklab, ${color} ${ghost ? 26 : 55}%, transparent)`;

  return (
    <div
      className="bar-grow-y relative"
      style={
        {
          width: 56,
          height,
          marginRight: DEPTH,
          animationDelay: `${delay}ms`,
        } as React.CSSProperties
      }
    >
      {/* Right face, a parallelogram sheared upward from the front edge. */}
      <div
        className="absolute top-0 left-full origin-bottom-left"
        style={{
          width: DEPTH,
          height,
          background: side,
          transform: `skewY(-45deg)`,
          borderRight: ghost ? `1px dashed ${edge}` : "none",
        }}
      />
      {/* Top face. */}
      <div
        className="absolute bottom-full left-0 origin-bottom-left"
        style={{
          width: 56,
          height: DEPTH,
          background: top,
          transform: `skewX(-45deg)`,
          borderTop: ghost ? `1px dashed ${edge}` : "none",
        }}
      />
      {/* Front face. */}
      <div
        className="absolute inset-0"
        style={{
          background: front,
          border: ghost ? `1px dashed ${edge}` : "none",
        }}
      />
    </div>
  );
}
