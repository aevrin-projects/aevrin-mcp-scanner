"use client";

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/**
 * Chart primitives for the admin analytics page.
 *
 * Recharts here, hand-rolled SVG on the customer dashboard — a deliberate
 * split, not an inconsistency. The customer dashboard is the app's hottest
 * route and didn't justify ~90kB for three shapes we fully control. This
 * panel is internal, low-traffic, behind auth and 2FA, and needs axes,
 * tooltips, and responsive re-layout that would be real work to hand-roll.
 * Different constraints, different answer.
 *
 * Everything is driven by CSS variables so both themes work without a
 * second palette, and every chart is paired with the same numbers in text
 * elsewhere on the page — colour is never the only carrier.
 */

const AXIS = { fontSize: 11, fill: "var(--muted-foreground)" };

function TooltipBox({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean;
  payload?: Array<{ name?: string; dataKey?: string; value?: number; color?: string }>;
  label?: string;
  formatter?: (value: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="min-w-40 rounded-lg border border-border bg-popover p-3 shadow-lg">
      {label ? <p className="mb-2 text-xs font-medium text-muted-foreground">{label}</p> : null}
      <div className="space-y-1.5">
        {payload.map((entry, i) => (
          <div key={i} className="flex items-center justify-between gap-4 text-xs">
            <span className="flex items-center gap-1.5">
              <span
                className="size-2.5 rounded-full border-2 bg-background"
                style={{ borderColor: entry.color }}
                aria-hidden="true"
              />
              <span className="text-muted-foreground capitalize">
                {(entry.name ?? entry.dataKey ?? "").toString().replace(/_/g, " ")}
              </span>
            </span>
            <span className="font-semibold tabular-nums">
              {formatter ? formatter(entry.value ?? 0) : (entry.value ?? 0).toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Trend over time, with a filled area under the primary series. */
export function TrendChart({
  data,
  xKey,
  series,
  height = 260,
  formatter,
}: {
  data: Array<Record<string, unknown>>;
  xKey: string;
  series: Array<{ key: string; label: string; color: string; dashed?: boolean }>;
  height?: number;
  formatter?: (v: number) => string;
}) {
  if (data.length === 0) {
    return <Empty height={height} />;
  }
  const primary = series[0];
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
        <defs>
          <linearGradient id={`grad-${primary.key}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={primary.color} stopOpacity={0.28} />
            <stop offset="100%" stopColor={primary.color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="4 4" stroke="var(--border)" vertical={false} />
        <XAxis dataKey={xKey} axisLine={false} tickLine={false} tick={AXIS} tickMargin={10} minTickGap={24} />
        <YAxis axisLine={false} tickLine={false} tick={AXIS} tickMargin={8} allowDecimals={false} width={38} />
        <Tooltip content={<TooltipBox formatter={formatter} />} cursor={{ stroke: "var(--border)", strokeWidth: 1 }} />
        <Area
          type="monotone"
          dataKey={primary.key}
          stroke="transparent"
          fill={`url(#grad-${primary.key})`}
          strokeWidth={0}
        />
        {series.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={s.color}
            strokeWidth={2}
            strokeDasharray={s.dashed ? "4 4" : undefined}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: s.color, fill: "var(--background)" }}
          />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Horizontal ranking — the right shape when the category label is long. */
export function RankedBars({
  data,
  labelKey,
  valueKey,
  color = "var(--brand)",
  height = 260,
}: {
  data: Array<Record<string, unknown>>;
  labelKey: string;
  valueKey: string;
  color?: string;
  height?: number;
}) {
  if (data.length === 0) return <Empty height={height} />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="4 4" stroke="var(--border)" horizontal={false} />
        <XAxis type="number" axisLine={false} tickLine={false} tick={AXIS} allowDecimals={false} />
        <YAxis
          type="category"
          dataKey={labelKey}
          axisLine={false}
          tickLine={false}
          tick={AXIS}
          width={150}
          // Long paths and referrer URLs would otherwise blow out the axis.
          tickFormatter={(v: string) => (v.length > 22 ? `${v.slice(0, 21)}…` : v)}
        />
        <Tooltip content={<TooltipBox />} cursor={{ fill: "var(--muted)", opacity: 0.4 }} />
        <Bar dataKey={valueKey} fill={color} radius={[0, 4, 4, 0]} maxBarSize={22} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Composition. Donut rather than pie so the total can live in the middle. */
export function Donut({
  data,
  height = 220,
  colors,
}: {
  data: Array<{ name: string; value: number }>;
  height?: number;
  colors: string[];
}) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  if (total === 0) return <Empty height={height} />;
  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="88%" paddingAngle={2} strokeWidth={0}>
            {data.map((_, i) => (
              <Cell key={i} fill={colors[i % colors.length]} />
            ))}
          </Pie>
          <Tooltip content={<TooltipBox />} />
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-semibold tabular-nums">{total.toLocaleString()}</span>
        <span className="text-[11px] text-muted-foreground">total</span>
      </div>
    </div>
  );
}

function Empty({ height }: { height: number }) {
  return (
    <div className="flex items-center justify-center rounded-lg border border-dashed border-border" style={{ height }}>
      <p className="text-sm text-muted-foreground">No data in this window.</p>
    </div>
  );
}
