import { LayoutDashboard, ScanSearch } from "lucide-react";

/**
 * A cropped preview of the real product, framed as a device that bleeds off
 * the right and bottom edges of the auth panel; you're looking *into* the
 * app, not at a floating brochure card.
 *
 * Everything shown is a plausible Aevrin dashboard in the product's own
 * shape. Deliberately not an aggregate marketing stat ("12,000 vulnerabilities
 * caught"), that would be a claim about our track record we can't
 * substantiate. A representative workspace sells the product just as well.
 *
 * Entirely `aria-hidden`: every claim it implies is stated in the copy beside
 * it, so a screen reader loses nothing by skipping the whole thing.
 */

const NAV = ["Overview", "Scans", "Usage", "Billing"];

// Two relative series, drawn as smooth polylines. Shapes only; the axis is
// labelled with months but carries no absolute scale, and nothing in the app
// reads these numbers.
const FINDINGS_SERIES = "0,58 26,52 52,61 78,44 104,49 130,33 156,38 182,22 208,27 234,14 260,19 286,8";
const RESOLVED_SERIES = "0,72 26,70 52,74 78,66 104,71 130,62 156,68 182,58 208,63 234,55 260,60 286,52";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"];

const SCAN_ROWS = [
  { target: "Synvoya/codeinspectus", score: 56, severity: "Critical", tone: "critical" },
  { target: "acme/mcp-notes-server", score: 71, severity: "High", tone: "high" },
  { target: "mcp.example.dev/sse", score: 88, severity: "Low", tone: "low" },
] as const;

const TONE_CLASS = {
  critical: "border-severity-critical/40 bg-severity-critical/10 text-severity-critical",
  high: "border-severity-high/40 bg-severity-high/10 text-severity-high",
  low: "border-severity-low/40 bg-severity-low/10 text-severity-low",
} as const;

export function AuthPreviewVisual() {
  return (
    <div aria-hidden="true" className="pointer-events-none relative select-none">
      {/* Wider than its container and clipped by the panel, so the frame runs
          off the edge instead of ending in an awkward margin. */}
      <div className="w-[min(112%,820px)] overflow-hidden rounded-l-2xl border-y border-l border-border bg-card shadow-2xl shadow-black/60">
        <div className="flex items-center gap-1.5 border-b border-border px-4 py-2.5">
          <span className="size-2.5 rounded-full bg-severity-critical/60" />
          <span className="size-2.5 rounded-full bg-severity-medium/60" />
          <span className="size-2.5 rounded-full bg-chart-1/60" />
        </div>

        {/* App nav */}
        <div className="flex items-center gap-5 border-b border-border px-5 py-3">
          <span className="flex items-center gap-2">
            <ScanSearch className="size-4 text-brand" />
            <span className="text-[12px] font-semibold tracking-tight">Aevrin</span>
          </span>
          {NAV.map((item, index) => (
            <span
              key={item}
              className={index === 0 ? "text-[11.5px] text-foreground" : "text-[11.5px] text-muted-foreground"}
            >
              {item}
            </span>
          ))}
        </div>

        <div className="space-y-5 p-5">
          <div>
            <h3 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight">
              <LayoutDashboard className="size-3.5 text-muted-foreground" />
              Overview
            </h3>
            <p className="mt-1 text-[11.5px] text-muted-foreground">
              Open findings across every repository, server, and config you scan.
            </p>
          </div>

          <div>
            <p className="text-[12px]">
              Open findings <span className="text-chart-1">−41%</span>
            </p>
            <svg viewBox="0 0 286 80" className="mt-3 h-24 w-full" preserveAspectRatio="none">
              {[16, 40, 64].map((y) => (
                <line key={y} x1="0" y1={y} x2="286" y2={y} stroke="var(--border)" strokeWidth="0.5" />
              ))}
              <polyline
                points={RESOLVED_SERIES}
                fill="none"
                stroke="var(--muted-foreground)"
                strokeOpacity="0.45"
                strokeWidth="1.25"
                strokeLinejoin="round"
              />
              <polyline
                points={FINDINGS_SERIES}
                fill="none"
                stroke="var(--brand)"
                strokeWidth="1.75"
                strokeLinejoin="round"
              />
            </svg>
            <div className="mt-2 flex justify-between text-[9.5px] text-muted-foreground">
              {MONTHS.map((month) => (
                <span key={month}>{month}</span>
              ))}
            </div>
          </div>

          <div>
            <p className="text-[12px] font-medium">
              Recent scans <span className="text-muted-foreground">3</span>
            </p>
            <div className="mt-3 space-y-px">
              <div className="flex items-center justify-between border-b border-border pb-2 text-[10px] text-muted-foreground">
                <span>Target</span>
                <span className="flex items-center gap-6">
                  <span>Top severity</span>
                  <span className="w-8 text-right">Score</span>
                </span>
              </div>
              {SCAN_ROWS.map((row) => (
                <div
                  key={row.target}
                  className="flex items-center justify-between border-b border-border/60 py-2.5 last:border-0"
                >
                  <span className="flex items-center gap-2.5">
                    <span className="size-5 shrink-0 rounded-full bg-muted" />
                    <span className="font-mono text-[10.5px] text-foreground">{row.target}</span>
                  </span>
                  <span className="flex items-center gap-6">
                    <span
                      className={`rounded-full border px-2 py-0.5 text-[9.5px] font-medium ${TONE_CLASS[row.tone]}`}
                    >
                      {row.severity}
                    </span>
                    <span className="w-8 text-right text-[11px] font-medium tabular-nums">{row.score}</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
