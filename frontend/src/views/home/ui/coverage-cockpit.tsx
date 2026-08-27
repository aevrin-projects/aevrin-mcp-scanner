"use client";

import { useEffect, useRef, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, XAxis } from "recharts";
import { useInView, useMotionValueEvent, useReducedMotion, useSpring } from "motion/react";
import { AlertTriangle, Check } from "lucide-react";

/**
 * The analytical chart cockpit, ported from the `advanced-stats` block.
 *
 * The signature is the clipped area chart: the series is drawn twice, once as
 * a faint ghost at 0.1 opacity and once as the real filled area whose
 * `clipPath` inset is driven by a motion spring, so the chart reveals itself
 * up to the pointer and a dashed rule plus a value chip track the same x.
 * Those exact mechanics, the spring damping and stiffness, the double Area,
 * the inset clip, the 3-3 dash, the two-line CartesianGrid, are kept from the
 * source rather than replaced with a generic gradient.
 *
 * The data is this product's, not the source's revenue series: open findings
 * per scan for one target. Below the chart the same panel carries the stage
 * list, using the block's border-led structure (hairline dividers, no nested
 * filled cards) so the coverage admission sits inside the instrument panel
 * rather than in a separate box.
 *
 * With `prefers-reduced-motion` the spring is skipped and the chart renders
 * fully drawn, since the reveal is the entire animation.
 */

type Point = { label: string; findings: number };

const SERIES: Point[] = [
  { label: "Scan 1", findings: 12 },
  { label: "Scan 2", findings: 9 },
  { label: "Scan 3", findings: 11 },
  { label: "Scan 4", findings: 7 },
  { label: "Scan 5", findings: 8 },
  { label: "Scan 6", findings: 5 },
];

const STAGES: { name: string; status: "done" | "failed"; note: string }[] = [
  { name: "Cloning", status: "done", note: "Completed" },
  { name: "Static analysis", status: "done", note: "Completed" },
  { name: "Secrets", status: "failed", note: "No Docker daemon" },
  { name: "Dependencies", status: "failed", note: "No Docker daemon" },
  { name: "Tool descriptions", status: "done", note: "Completed" },
  { name: "Aggregating", status: "done", note: "Completed" },
];

// Read from the marketing tokens at mount so the series follows the theme;
// a literal would be too dark on the light panel or too dark on the dark one.
const ACCENT_FALLBACK = "#2f9e68";

export function CoverageCockpit() {
  const chartRef = useRef<HTMLDivElement>(null);
  const [axis, setAxis] = useState(0);
  const [value, setValue] = useState(SERIES[SERIES.length - 1].findings);
  const reduceMotion = useReducedMotion();

  const [accent, setAccent] = useState(ACCENT_FALLBACK);
  useEffect(() => {
    // Read off the chart element, not documentElement: --mk-accent-chart is
    // declared on `.marketing`, so resolving it against :root returned the
    // light value forever and the series never followed the theme.
    const read = () => {
      const element = chartRef.current;
      if (!element) return;
      const value = getComputedStyle(element).getPropertyValue("--mk-accent-chart").trim();
      if (value) setAccent(value);
    };
    read();
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  const springX = useSpring(0, { damping: 30, stiffness: 100 });
  const springY = useSpring(SERIES[SERIES.length - 1].findings, { damping: 30, stiffness: 100 });

  useMotionValueEvent(springX, "change", (latest) => setAxis(latest));
  useMotionValueEvent(springY, "change", (latest) => setValue(Math.round(latest)));

  // The upstream block reads `chartRef.current` straight out of render to
  // size the clip, which React forbids and which also silently produces a
  // width of 0 on the first paint. Measured into state instead, and kept in
  // step with a ResizeObserver so the reveal stays correct after a reflow.
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = chartRef.current;
    if (!element) return;
    const measure = () => setWidth(element.getBoundingClientRect().width);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // The source only ever opens the clip in response to a pointer, so on a
  // touch screen, or before anyone moves the mouse, the chart sits invisible
  // behind a full-width inset. Opening it when the panel scrolls into view is
  // what makes the series "draw into view" the brief asks for; the pointer
  // then takes over from wherever the reveal finished.
  const inView = useInView(chartRef, { once: true, amount: 0.4 });
  useEffect(() => {
    if (width <= 0) return;
    if (inView) {
      springX.set(width);
      return;
    }
    // Same safety net as this codebase's `Reveal`: the un-revealed state is a
    // full-width clip, so if the observer never fires the chart would simply
    // never appear. A reveal must not be able to hide real content.
    const fallback = window.setTimeout(() => springX.set(width), 2000);
    return () => window.clearTimeout(fallback);
  }, [inView, width, springX]);

  // With motion off the clip is opened fully, otherwise the chart would sit
  // permanently hidden behind an inset that never animates.
  const clip = reduceMotion ? undefined : `inset(0 ${Math.max(0, width - axis)}px 0 0)`;

  return (
    <div
      className="rounded-3xl p-6 sm:p-8"
      style={{ background: "var(--mk-panel)", border: "1px solid var(--mk-line)" }}
    >
      <div className="flex flex-wrap items-start justify-between gap-4 pb-4">
        <div>
          <h3 className="text-lg font-bold tracking-tight">Open findings per scan</h3>
          <p className="mk-mono mt-1">github.com/example/mcp-server</p>
        </div>
        <div className="text-right">
          <div className="flex items-baseline justify-end gap-2">
            <span className="font-mono text-2xl font-semibold tabular-nums">{value}</span>
            <span
              className="rounded px-1.5 py-0.5 text-xs font-bold"
              style={{
                color: "var(--mk-ink)",
                background: "color-mix(in oklab, var(--mk-accent-chart) 26%, transparent)",
              }}
            >
              open
            </span>
          </div>
          <p className="mt-0.5 text-[13px]" style={{ color: "var(--mk-muted)" }}>
            Latest run, worst first
          </p>
        </div>
      </div>

      {/* Decorative: the same figures are in the heading above and the
          coverage list below. recharts puts a tabindex on its own wrapper, so
          `aria-hidden` alone would leave a focusable node inside a hidden
          subtree, which is an accessibility violation in its own right. The
          tab stop is removed rather than the hiding. */}
      <div
        ref={chartRef}
        aria-hidden="true"
        className="h-52 w-full [&_.recharts-wrapper]:outline-none"
        style={{ ["--accent" as string]: accent }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            className="overflow-visible"
            tabIndex={-1}
            data={SERIES}
            // Small side margins so the first and last ticks are not half
            // clipped by the plot edge; the source runs flush and loses "Scan 1".
            margin={{ top: 22, right: 14, left: 14, bottom: 0 }}
            onMouseMove={(state) => {
              // recharts 3 dropped `activePayload` from the handler's public
              // type while still passing it, which is why the upstream block
              // casts here. Narrowed to the one field actually read rather
              // than casting the whole state to `any`.
              const { activeCoordinate, activePayload } = state as typeof state & {
                activePayload?: { value?: number }[];
              };
              const x = activeCoordinate?.x;
              const point = activePayload?.[0]?.value;
              if (x && typeof point === "number") {
                springX.set(x);
                springY.set(point);
              }
            }}
            onMouseLeave={() => {
              springX.set(width);
              springY.jump(SERIES[SERIES.length - 1].findings);
            }}
          >
            <CartesianGrid
              vertical={false}
              strokeDasharray="3 3"
              stroke="var(--mk-line)"
              horizontalCoordinatesGenerator={({ height }) => [22, height - 30]}
            />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              tick={{ fill: "var(--mk-muted)", fontSize: 12 }}
            />

            {/* Ghost line behind the graph, so the un-revealed part of the
                series is still legible as a shape. */}
            <Area
              dataKey="findings"
              type="monotone"
              fill="none"
              stroke={accent}
              strokeOpacity={0.18}
              isAnimationActive={false}
            />

            <Area
              dataKey="findings"
              type="monotone"
              fill="url(#coverage-area)"
              fillOpacity={0.4}
              stroke={accent}
              strokeWidth={2}
              clipPath={clip}
              isAnimationActive={false}
            />

            {!reduceMotion && axis > 0 ? (
              <>
                <line
                  x1={axis}
                  y1={22}
                  x2={axis}
                  y2="85%"
                  stroke={accent}
                  strokeDasharray="3 3"
                  strokeLinecap="round"
                  strokeOpacity={0.35}
                />
                <rect x={axis - 46} y={0} width={46} height={18} rx={3} fill={accent} />
                <text
                  x={axis - 23}
                  y={13}
                  fontWeight={600}
                  fontSize={11}
                  textAnchor="middle"
                  fill="var(--mk-accent-contrast)"
                >
                  {value} open
                </text>
              </>
            ) : null}

            <defs>
              <linearGradient id="coverage-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={accent} stopOpacity={0.5} />
                <stop offset="95%" stopColor={accent} stopOpacity={0} />
              </linearGradient>
            </defs>
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Border-led structure: the coverage list is dividers, not a nested card. */}
      <div className="mt-6 border-t pt-2" style={{ borderColor: "var(--mk-line)" }}>
        <p className="mk-mono py-2">Coverage, this run</p>
        <ul>
          {STAGES.map((stage) => (
            <li
              key={stage.name}
              className="flex items-center justify-between gap-3 border-t py-2.5 font-mono"
              style={{ borderColor: "var(--mk-line-soft)" }}
            >
              <span className="flex min-w-0 items-center gap-2.5">
                {stage.status === "done" ? (
                  <Check className="size-4 shrink-0 text-chart-1" aria-hidden="true" />
                ) : (
                  <AlertTriangle
                    className="size-4 shrink-0 text-severity-high"
                    aria-hidden="true"
                  />
                )}
                <span className="truncate text-[13px]">{stage.name}</span>
              </span>
              <span
                className="shrink-0 text-[12px]"
                style={
                  stage.status === "done"
                    ? { color: "var(--mk-muted)" }
                    : { color: "var(--color-severity-high)" }
                }
              >
                {stage.note}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
