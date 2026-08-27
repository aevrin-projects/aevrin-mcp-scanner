"use client";

import {
  Activity,
  Boxes,
  ChevronDown,
  Clock,
  GitBranch,
  KeyRound,
  LayoutGrid,
  Laptop,
  ScanLine,
  ShieldCheck,
  Sparkles,
  Server,
  Waypoints,
} from "lucide-react";
import Image from "next/image";
import {
  ScoreGauge,
  SeverityDonut,
  SeverityTrendChart,
  type SeverityCounts,
  type TrendPoint,
} from "@/shared/ui/severity-charts";

/**
 * The Aevrin dashboard, rendered at preview scale.
 *
 * This is not a drawing of the product. The gauge, the stacked severity
 * history and the donut are the same three components the signed-in
 * Overview screen mounts, imported from `severity-charts`, so the preview
 * cannot drift away from the real thing: change a chart and this changes
 * with it. The chrome around them (sidebar, top bar, stat row, panel
 * headings) mirrors the real Overview section for section.
 *
 * The figures are a representative workspace, not a claim about anyone's
 * track record. They are internally consistent on purpose: the severity
 * counts in the stat row, the donut and its legend are one set of numbers,
 * so nothing here says two different things at once.
 *
 * Entirely `aria-hidden`. Every claim it implies is stated in the copy
 * beside it, so a screen reader loses nothing by skipping it.
 */

const OPEN_COUNTS: SeverityCounts = { critical: 1, high: 8, medium: 15, low: 21 };
const OPEN_TOTAL = OPEN_COUNTS.critical + OPEN_COUNTS.high + OPEN_COUNTS.medium + OPEN_COUNTS.low;

const TREND: TrendPoint[] = [
  { id: "1", label: "Aug 25", counts: { critical: 3, high: 4, medium: 4, low: 5 } },
  { id: "2", label: "Aug 25", counts: { critical: 0, high: 0, medium: 4, low: 6 } },
  { id: "3", label: "Aug 26", counts: { critical: 0, high: 0, medium: 4, low: 6 } },
  { id: "4", label: "Aug 26", counts: { critical: 0, high: 0, medium: 3, low: 6 } },
  { id: "5", label: "Aug 26", counts: { critical: 0, high: 0, medium: 1, low: 0 } },
  { id: "6", label: "Aug 26", counts: { critical: 0, high: 0, medium: 1, low: 0 } },
];

const SIDEBAR: { group: string; items: { label: string; icon: typeof LayoutGrid }[] }[] = [
  { group: "", items: [{ label: "Overview", icon: LayoutGrid }] },
  {
    group: "AI security",
    items: [
      { label: "Agents", icon: Sparkles },
      { label: "Devices", icon: Laptop },
      { label: "MCP servers", icon: Server },
      { label: "Skills", icon: Boxes },
      { label: "Permissions", icon: ShieldCheck },
      { label: "Attack paths", icon: Waypoints },
    ],
  },
  {
    group: "Scanning",
    items: [
      { label: "New scan", icon: ScanLine },
      { label: "History", icon: Clock },
    ],
  },
  { group: "Automation", items: [{ label: "Hooks and CI", icon: GitBranch }] },
  {
    group: "Account",
    items: [
      { label: "Usage", icon: Activity },
      { label: "API keys", icon: KeyRound },
    ],
  },
];

const STATS = (c: SeverityCounts, at: (n: number) => number) => [
  { label: "Critical", value: c.critical, note: "Open findings", tone: "text-severity-critical" },
  { label: "High", value: c.high, note: "Open findings", tone: "text-severity-high" },
  { label: "Needs attention", value: at(4), note: "Failed or partial scans", tone: "text-foreground" },
  { label: "Targets", value: at(4), note: "Repos, servers, configs", tone: "text-foreground" },
];

const LEGEND = (c: SeverityCounts) => [
  { label: "Critical", value: c.critical, dot: "bg-severity-critical" },
  { label: "High", value: c.high, dot: "bg-severity-high" },
  { label: "Medium", value: c.medium, dot: "bg-severity-medium" },
  { label: "Low", value: c.low, dot: "bg-severity-low" },
];

export function DashboardPreview({
  className = "",
  reveal = 1,
}: {
  className?: string;
  /**
   * How far the dashboard has drawn itself in, 0 to 1.
   *
   * Every figure below is derived from it, so the gauge arc, the donut ring,
   * the severity counts and the stat row all advance together and land on
   * their real values at 1. The caller drives this from scroll position, which
   * is why nothing here animates on its own clock.
   *
   * The stacked bars are the exception: their heights are proportions of the
   * busiest column, so scaling the data would leave them at a constant height.
   * They are scrubbed through their existing keyframes by the `--reveal`
   * custom property instead.
   */
  reveal?: number;
}) {
  const t = Math.max(0, Math.min(1, reveal));
  const at = (value: number) => Math.round(value * t);
  const counts: SeverityCounts = {
    critical: at(OPEN_COUNTS.critical),
    high: at(OPEN_COUNTS.high),
    medium: at(OPEN_COUNTS.medium),
    low: at(OPEN_COUNTS.low),
  };
  const openNow = counts.critical + counts.high + counts.medium + counts.low;

  return (
    <div
      aria-hidden="true"
      className={`preview-scrub pointer-events-none select-none overflow-hidden rounded-xl border border-border bg-background text-foreground shadow-2xl shadow-black/25 ${className}`}
      style={{ ["--reveal" as string]: t }}
    >
      <div className="flex min-h-[420px]">
        {/* Sidebar */}
        <aside className="hidden w-[168px] shrink-0 flex-col gap-3 border-r border-border bg-sidebar px-3 py-3.5 sm:flex">
          <div className="flex items-center gap-2 px-1.5 pb-1">
            <Image src="/logo.png" alt="" width={16} height={17} />
            <span className="text-[11px] font-semibold tracking-[0.14em] uppercase">Aevrin</span>
          </div>
          {SIDEBAR.map((section) => (
            <div key={section.group || "root"} className="space-y-0.5">
              {section.group ? (
                <p className="px-1.5 pt-1 pb-1 text-[8.5px] font-semibold tracking-[0.14em] text-muted-foreground uppercase">
                  {section.group}
                </p>
              ) : null}
              {section.items.map((item) => {
                const active = item.label === "Overview";
                return (
                  <div
                    key={item.label}
                    className={`flex items-center gap-2 rounded px-1.5 py-1 text-[10.5px] ${
                      active ? "bg-accent text-foreground" : "text-muted-foreground"
                    }`}
                  >
                    <item.icon className="size-3 shrink-0" />
                    <span className="truncate">{item.label}</span>
                  </div>
                );
              })}
            </div>
          ))}
        </aside>

        {/* Main */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-end gap-2 border-b border-border px-4 py-2.5">
            <span className="rounded border border-border px-2 py-1 text-[10px] font-medium">New scan</span>
            <span className="grid size-5 place-items-center rounded bg-muted text-[8px] font-semibold">UJ</span>
            <ChevronDown className="size-3 text-muted-foreground" />
          </div>

          <div className="space-y-3.5 p-4">
            <div>
              <p className="text-[8.5px] font-semibold tracking-[0.14em] text-muted-foreground uppercase">
                Overview
              </p>
              <h3 className="mt-1 text-[17px] font-semibold tracking-tight">Dashboard</h3>
              <p className="mt-0.5 text-[10.5px] text-muted-foreground">
                Prioritize urgent findings, partial coverage, and the latest scan outcome.
              </p>
            </div>

            {/* Stat row */}
            <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
              {STATS(counts, at).map((stat) => (
                <div key={stat.label} className="rounded-lg border border-border bg-card px-3 py-2.5">
                  <p className="text-[8.5px] font-semibold tracking-[0.12em] text-muted-foreground uppercase">
                    {stat.label}
                  </p>
                  <p className={`mt-1 text-xl font-semibold tabular-nums ${stat.tone}`}>{stat.value}</p>
                  <p className="mt-0.5 text-[9px] text-muted-foreground">{stat.note}</p>
                </div>
              ))}
            </div>

            {/* Panels */}
            <div className="grid gap-2.5 lg:grid-cols-[1.55fr_1fr]">
              <div className="rounded-lg border border-border bg-card">
                <div className="border-b border-border px-3.5 py-2.5">
                  <p className="text-[11.5px] font-semibold">Security posture</p>
                  <p className="text-[9.5px] text-muted-foreground">
                    Latest score, and open findings per scan over time.
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <div className="flex shrink-0 flex-col items-center gap-1 border-r border-border px-3 py-3">
                    <ScoreGauge score={at(92)} size={92} />
                    <p className="max-w-[92px] truncate font-mono text-[8.5px] text-muted-foreground">
                      mcp.context7.com
                    </p>
                  </div>
                  <div className="min-w-0 flex-1 origin-left scale-[0.92]">
                    <SeverityTrendChart points={TREND} />
                  </div>
                </div>
              </div>

              <div className="rounded-lg border border-border bg-card">
                <div className="border-b border-border px-3.5 py-2.5">
                  <p className="text-[11.5px] font-semibold">Open findings</p>
                  <p className="text-[9.5px] text-muted-foreground">
                    Across every target, excluding triaged.
                  </p>
                </div>
                <div className="flex flex-col items-center gap-2.5 px-3.5 py-3">
                  <SeverityDonut
                    counts={counts}
                    total={OPEN_TOTAL}
                    displayTotal={openNow}
                    size={96}
                  />
                  <div className="w-full space-y-1">
                    {LEGEND(counts).map((row) => (
                      <div key={row.label} className="flex items-center justify-between text-[10px]">
                        <span className="flex items-center gap-1.5 text-muted-foreground">
                          <span className={`size-1.5 rounded-full ${row.dot}`} />
                          {row.label}
                        </span>
                        <span className="font-medium tabular-nums">{row.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
