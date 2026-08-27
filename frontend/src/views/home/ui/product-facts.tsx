"use client";

import { useRef } from "react";
import { Layers, ShieldAlert, TerminalSquare, Wrench } from "lucide-react";
import { TimelineAnimation } from "@/shared/ui/timeline-animation";
import { CoverageCockpit } from "./coverage-cockpit";

/**
 * Built on the `advanced-stats` layout: one large instrument panel, a stacked
 * pair beside it, and a row of figures underneath. The figure cards use the
 * `stats-details` treatment, an orange marker tile that fills on hover and a
 * repeated low-opacity icon behind the content for texture.
 *
 * The block set's accent is orange; this uses green, matching the product's
 * own mark, on the icon tiles and the chart series. It is a decorative marker
 * only and never encodes a result: severities keep the severity tokens, so
 * amber and red still mean `high` and `critical` and nothing else.
 *
 * The figures are not traction metrics. "Revenue growth +142%" and the rest of
 * that genre are claims about a company and every one of them here would be
 * invented. These four are properties of the product that can be checked
 * against the source: the tool list in `ToolName`, the OWASP MCP categories the
 * rules map to, the stage list in `StageName`, and the CLI's exit codes.
 */

const FACTS = [
  {
    icon: Wrench,
    value: "10",
    label: "Scanners",
    body: "Open-source tools run per scan, normalised into one severity scale.",
  },
  {
    icon: ShieldAlert,
    value: "9",
    label: "OWASP MCP categories",
    body: "Every finding is mapped to one, so a report survives a compliance thread.",
  },
  {
    icon: Layers,
    value: "6",
    label: "Scan stages",
    body: "Each reports its own outcome. A stage that failed is never counted as passed.",
  },
  {
    icon: TerminalSquare,
    value: "4",
    label: "Exit codes",
    body: "0 clean, 1 findings, 2 error, 3 incomplete. CI can tell those apart.",
  },
];

// What the run in the panel beside this actually returns, and why. The card
// used to hold only a heading and a progress bar with a large void between
// them; these rows are the substance that was missing.
const EXIT_CODES = [
  { code: "0", meaning: "Clean", active: false },
  { code: "1", meaning: "Findings", active: false },
  { code: "2", meaning: "Error", active: false },
  { code: "3", meaning: "Incomplete", active: true },
];

export function ProductFacts() {
  const timelineRef = useRef<HTMLDivElement>(null);

  return (
    <section ref={timelineRef} className="px-6 py-20 lg:py-28">
      <div className="mx-auto max-w-6xl">
        <div className="max-w-2xl">
          <TimelineAnimation animationNum={0} timelineRef={timelineRef} as="p" className="mk-mono">
            What a scan returns
          </TimelineAnimation>
          <TimelineAnimation
            animationNum={1}
            timelineRef={timelineRef}
            as="h2"
            className="mk-h2 mt-4"
          >
            A result that admits what it could not check.
          </TimelineAnimation>
          <TimelineAnimation
            animationNum={2}
            timelineRef={timelineRef}
            as="p"
            className="mk-lede mt-5"
          >
            Most scanners return a number. A number from a run where half the checks failed is
            worse than no number at all, so every Aevrin report carries its own coverage beside
            the score.
          </TimelineAnimation>
        </div>

        <div className="mt-12 grid gap-6 lg:grid-cols-3">
          <TimelineAnimation animationNum={3} timelineRef={timelineRef} className="lg:col-span-2">
            <CoverageCockpit />
          </TimelineAnimation>

          <div className="flex flex-col gap-6">
            <TimelineAnimation
              animationNum={4}
              timelineRef={timelineRef}
              className="flex flex-col rounded-3xl p-7"
              style={{ background: "var(--mk-invert-bg)", color: "var(--mk-invert-fg)" }}
            >
              <p
                className="text-[10px] font-semibold tracking-[0.2em] uppercase"
                style={{ color: "var(--mk-invert-muted)" }}
              >
                The rule that does not bend
              </p>
              <h3 className="mt-3 text-xl font-bold tracking-tight">
                Incomplete is never reported as clean
              </h3>

              <div className="mt-6">
                <div className="mb-2 flex items-end justify-between">
                  <span className="font-mono text-3xl font-semibold tracking-tighter">4 / 6</span>
                  <span className="mb-1 text-xs" style={{ color: "var(--mk-invert-muted)" }}>
                    stages completed
                  </span>
                </div>
                <div
                  className="h-1.5 w-full overflow-hidden rounded-full"
                  style={{ background: "color-mix(in oklab, var(--mk-invert-fg) 18%, transparent)" }}
                >
                  <div
                    className="h-full rounded-full"
                    style={{ width: "66.6%", background: "var(--mk-invert-fg)" }}
                  />
                </div>
              </div>

              {/* Border-led rows rather than a nested card. */}
              <ul className="mt-6 font-mono">
                {EXIT_CODES.map((row) => (
                  <li
                    key={row.code}
                    className="flex items-center justify-between gap-3 border-t py-2"
                    style={{
                      borderColor: "color-mix(in oklab, var(--mk-invert-fg) 14%, transparent)",
                      color: row.active ? "var(--mk-invert-fg)" : "var(--mk-invert-muted)",
                    }}
                  >
                    <span className="text-[13px]">exit {row.code}</span>
                    <span className="flex items-center gap-2 text-[13px]">
                      {row.meaning}
                      {row.active ? (
                        <span
                          className="rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wider uppercase"
                          style={{
                            background: "color-mix(in oklab, var(--mk-invert-fg) 16%, transparent)",
                          }}
                        >
                          This run
                        </span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>

              <p className="mt-5 text-[13px]" style={{ color: "var(--mk-invert-muted)" }}>
                A pipeline that treats exit 3 as a pass has to say so out loud.
              </p>
            </TimelineAnimation>

            <TimelineAnimation
              animationNum={5}
              timelineRef={timelineRef}
              className="rounded-3xl p-7"
              style={{ background: "var(--mk-panel)", border: "1px solid var(--mk-line)" }}
            >
              <h3 className="font-bold tracking-tight">Every finding carries a location</h3>
              <p className="mt-2.5 text-sm leading-relaxed" style={{ color: "var(--mk-muted)" }}>
                File, line, the scanner that raised it, the OWASP category it maps to, and a
                remediation you can act on. Not a severity badge on its own.
              </p>
            </TimelineAnimation>
          </div>
        </div>

        {/* Figures, in the stats-details treatment. */}
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FACTS.map((fact, index) => (
            <TimelineAnimation
              key={fact.label}
              animationNum={6 + index}
              timelineRef={timelineRef}
              className="group relative overflow-hidden rounded-2xl p-8 transition-colors"
              style={{ background: "var(--mk-panel)", border: "1px solid var(--mk-line)" }}
            >
              {/* Low-opacity icon pattern: the card's own mark, repeated as
                  texture. Replaces the source's stock photograph, which would
                  have been a network request for decoration. */}
              <div
                aria-hidden="true"
                className="pointer-events-none absolute -top-6 -right-8 opacity-[0.04] transition-opacity duration-300 group-hover:opacity-[0.09]"
              >
                <fact.icon className="size-40" strokeWidth={1} />
              </div>

              <article className="relative z-10">
                {/* Background and border are classes, not inline styles. An
                    inline `background` beats a `group-hover:bg-*` class, so the
                    tile kept its white fill on hover while `group-hover:
                    text-white` still applied, turning the icon white on white
                    and making it vanish exactly when you pointed at it. */}
                <div className="mb-6 grid size-8 place-items-center rounded-lg border border-[var(--mk-line)] bg-[var(--mk-raise)] transition-colors group-hover:border-[var(--mk-accent)] group-hover:bg-[var(--mk-accent)] group-hover:text-[var(--mk-accent-contrast)]">
                  <fact.icon className="size-4" />
                </div>
                <h3
                  className="mb-2 text-xs font-bold tracking-widest uppercase"
                  style={{ color: "var(--mk-muted)" }}
                >
                  {fact.label}
                </h3>
                <p className="mb-4 font-mono text-4xl font-semibold tracking-tight">{fact.value}</p>
                <p className="text-sm leading-relaxed" style={{ color: "var(--mk-muted)" }}>
                  {fact.body}
                </p>
              </article>
            </TimelineAnimation>
          ))}
        </div>
      </div>
    </section>
  );
}
