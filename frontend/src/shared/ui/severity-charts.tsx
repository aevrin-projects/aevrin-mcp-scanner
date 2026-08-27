"use client";

/**
 * Dashboard data visuals, hand-rolled in SVG/CSS rather than pulled from a
 * charting library. At this scale (one gauge, one stacked bar chart, one
 * donut) a library would add ~90kB to the app's heaviest route to render
 * three shapes we fully control, and none of these need axes, tooltips,
 * zoom, or responsive re-layout of the kind that justifies one.
 *
 * Every chart here is `aria-hidden` and paired with a real, readable value
 * or list in the DOM. The picture is the summary; the text is the data.
 */

const SEVERITY_TOKENS = {
  critical: "var(--severity-critical)",
  high: "var(--severity-high)",
  medium: "var(--severity-medium)",
  low: "var(--severity-low)",
} as const;

export type SeverityCounts = {
  critical: number;
  high: number;
  medium: number;
  low: number;
};

/* ------------------------------------------------------------------ gauge */

/** Score band → color. Matches how the product talks about scores elsewhere:
 *  a score is a risk signal, so the color is a severity color, not the brand
 *  accent. A 40/100 rendered in calm blue would undersell the result. */
function scoreBand(score: number) {
  if (score >= 80) return { color: "var(--chart-1)", label: "Low risk" };
  if (score >= 60) return { color: "var(--severity-medium)", label: "Moderate risk" };
  if (score >= 40) return { color: "var(--severity-high)", label: "Significant risk" };
  return { color: "var(--severity-critical)", label: "Severe risk" };
}

export function ScoreGauge({ score, size = 132 }: { score: number | null; size?: number }) {
  const radius = size / 2 - 9;
  const circumference = 2 * Math.PI * radius;
  // 270° arc, opening at the bottom; a full ring reads as a progress spinner.
  const arcFraction = 0.75;
  const arcLength = circumference * arcFraction;
  const filled = score == null ? 0 : (Math.max(0, Math.min(100, score)) / 100) * arcLength;
  const band = score == null ? { color: "var(--muted-foreground)", label: "No scans yet" } : scoreBand(score);

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg
        aria-hidden="true"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="-rotate-[225deg]"
      >
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--muted)"
          strokeWidth={9}
          strokeLinecap="round"
          strokeDasharray={`${arcLength} ${circumference}`}
        />
        <circle
          className="gauge-sweep"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={band.color}
          strokeWidth={9}
          strokeLinecap="round"
          strokeDasharray={`${arcLength} ${circumference}`}
          style={
            {
              "--gauge-circumference": `${arcLength}`,
              "--gauge-offset": `${arcLength - filled}`,
            } as React.CSSProperties
          }
        />
      </svg>

      {/* The label stack scales with the ring. These sizes were fixed at
          32/10/11px whatever `size` was, so the three lines came to ~63px
          inside a 56px opening once the gauge was rendered smaller than its
          default, and the score sat on top of the arc. Ratios are taken from
          the default size so the dashboard's own gauge is unchanged. */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="leading-none font-semibold tracking-tight tabular-nums text-foreground"
          style={{ fontSize: `${(32 / 132) * size}px` }}
        >
          {score ?? "-"}
        </span>
        <span
          className="text-muted-foreground"
          style={{ fontSize: `${(10 / 132) * size}px`, marginTop: `${(4 / 132) * size}px` }}
        >
          out of 100
        </span>
        <span
          className="font-medium"
          style={{
            color: band.color,
            fontSize: `${(11 / 132) * size}px`,
            marginTop: `${(6 / 132) * size}px`,
          }}
        >
          {band.label}
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------- severity history */

export type TrendPoint = {
  id: string;
  label: string;
  counts: SeverityCounts;
};

/**
 * Stacked severity bars, one column per scan, oldest → newest. Bar heights
 * are relative to the busiest scan in the window; the y-axis is labelled with
 * that maximum so the scale is never implied.
 */
export function SeverityTrendChart({ points }: { points: TrendPoint[] }) {
  const totals = points.map((p) => p.counts.critical + p.counts.high + p.counts.medium + p.counts.low);
  const max = Math.max(...totals, 1);

  return (
    <div className="px-4 py-4">
      <div className="flex gap-3">
        {/* Scale labels, so the bars mean something without a tooltip. */}
        <div
          aria-hidden="true"
          className="flex h-32 w-6 shrink-0 flex-col justify-between text-right text-[10px] tabular-nums text-muted-foreground"
        >
          <span>{max}</span>
          <span>{Math.round(max / 2)}</span>
          <span>0</span>
        </div>

        {/* A grid rather than flex so the columns have a knowable width: the
            date labels below reuse the same track definition and therefore
            sit under the first and last bars, not at the panel's edges. Bars
            cap at 64px so three scans don't render as three wide slabs. */}
        <div
          className="grid h-32 min-w-0 flex-1 items-end gap-1.5"
          style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 64px))` }}
        >
          {points.map((point, index) => {
            const total = totals[index];
            const segments = (
              [
                ["critical", point.counts.critical],
                ["high", point.counts.high],
                ["medium", point.counts.medium],
                ["low", point.counts.low],
              ] as const
            ).filter(([, value]) => value > 0);

            return (
              <div key={point.id} className="group flex h-full min-w-0 flex-col justify-end">
                <div
                  className="bar-grow-y flex w-full flex-col-reverse overflow-hidden rounded-[3px]"
                  style={
                    {
                      height: `${Math.max((total / max) * 100, total > 0 ? 4 : 1.5)}%`,
                      "--i": index,
                    } as React.CSSProperties
                  }
                >
                  {total === 0 ? (
                    <div className="h-full w-full bg-muted" />
                  ) : (
                    segments.map(([severity, value]) => (
                      <div
                        key={severity}
                        className="w-full transition-opacity group-hover:opacity-80"
                        style={{
                          height: `${(value / total) * 100}%`,
                          background: SEVERITY_TOKENS[severity],
                        }}
                      />
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div aria-hidden="true" className="mt-2 flex gap-3 text-[10px] text-muted-foreground">
        <span className="w-6 shrink-0" />
        <div
          className="grid min-w-0 flex-1 gap-1.5"
          style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 64px))` }}
        >
          <span className="col-start-1 whitespace-nowrap">{points[0]?.label}</span>
          {points.length > 1 ? (
            <span className="whitespace-nowrap text-right" style={{ gridColumn: points.length }}>
              {points[points.length - 1]?.label}
            </span>
          ) : null}
        </div>
      </div>

      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-border pt-3">
        {(["critical", "high", "medium", "low"] as const).map((severity) => (
          <li key={severity} className="flex items-center gap-1.5 text-[11px] text-muted-foreground capitalize">
            <span
              aria-hidden="true"
              className="size-2 rounded-[2px]"
              style={{ background: SEVERITY_TOKENS[severity] }}
            />
            {severity}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ donut */

/**
 * Severity split as a donut with the total in the middle. Segments are drawn
 * with stroke-dasharray on a single circle, no path math, no library, and
 * it stays crisp at any size.
 */
export function SeverityDonut({
  counts,
  total,
  size = 116,
  displayTotal,
}: {
  counts: SeverityCounts;
  total: number;
  size?: number;
  /**
   * The figure shown in the middle, when it needs to differ from the
   * denominator the segments are measured against. The marketing preview
   * draws the ring in progressively by scaling `counts` while holding `total`
   * at its final value, and needs the centre number to count up with the
   * ring rather than sit at the end state. Defaults to `total`, so the
   * dashboard is unaffected.
   */
  displayTotal?: number;
}) {
  const radius = size / 2 - 8;
  const circumference = 2 * Math.PI * radius;

  let offset = 0;
  const segments = (
    [
      ["critical", counts.critical],
      ["high", counts.high],
      ["medium", counts.medium],
      ["low", counts.low],
    ] as const
  )
    .filter(([, value]) => value > 0)
    .map(([severity, value]) => {
      const length = (value / total) * circumference;
      const segment = { severity, value, length, offset };
      offset += length;
      return segment;
    });

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg aria-hidden="true" width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--muted)" strokeWidth={10} />
        {segments.map((segment) => (
          <circle
            key={segment.severity}
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={SEVERITY_TOKENS[segment.severity]}
            strokeWidth={10}
            // 1.5px visual gap between adjacent segments.
            strokeDasharray={`${Math.max(segment.length - 1.5, 0.5)} ${circumference}`}
            strokeDashoffset={-segment.offset}
          />
        ))}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-semibold tabular-nums text-foreground">
          {displayTotal ?? total}
        </span>
        <span className="text-[10px] text-muted-foreground">open</span>
      </div>
    </div>
  );
}
