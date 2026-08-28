"use client";

import { useRef } from "react";
import { Eye, KeyRound, PackageOpen, TerminalSquare } from "lucide-react";
import { TimelineAnimation } from "@/shared/ui/timeline-animation";

/**
 * The failure modes, in the `stats-details` treatment: hairline-bordered
 * cards, a marker tile that fills with the accent on hover, and the card's
 * own icon repeated behind the content at low opacity for texture.
 *
 * Each entry maps to an OWASP MCP category the scanner actually checks.
 */

const RISKS = [
  {
    icon: Eye,
    tag: "MCP02 Tool poisoning",
    title: "It ships a description the model obeys",
    body: "A tool description is instructions to your agent. Text hidden inside it can redirect behaviour without ever touching your code.",
  },
  {
    icon: KeyRound,
    tag: "MCP01 Token mismanagement",
    title: "It runs with your credentials",
    body: "Servers routinely hold tokens for the systems they reach. A leaked or over-scoped credential inherits everything you granted.",
  },
  {
    icon: TerminalSquare,
    tag: "MCP05 Command injection",
    title: "It executes on your machine",
    body: "A stdio server is a local process. An unescaped argument reaching a shell is command execution on the host.",
  },
  {
    icon: PackageOpen,
    tag: "MCP04 Rug pull",
    title: "It can change after you trust it",
    body: "Tool definitions can drift after install, and dependencies carry their own known vulnerabilities.",
  },
];

export function RiskSection() {
  const timelineRef = useRef<HTMLDivElement>(null);

  return (
    <section ref={timelineRef} className="px-6 py-20 lg:py-28">
      <div className="mx-auto max-w-6xl">
        <div className="max-w-3xl">
          <TimelineAnimation animationNum={0} timelineRef={timelineRef} as="p" className="mk-mono">
            The risk
          </TimelineAnimation>
          <TimelineAnimation
            animationNum={1}
            timelineRef={timelineRef}
            as="h2"
            className="mk-h2 mt-4"
          >
            An MCP server is code, credentials, and instructions your agent trusts.
          </TimelineAnimation>
          <TimelineAnimation
            animationNum={2}
            timelineRef={timelineRef}
            as="p"
            className="mk-lede mt-5"
          >
            Installing one grants real capability on your machine and in the systems it reaches.
            These are the failure modes Aevrin looks for.
          </TimelineAnimation>
        </div>

        <div className="mt-12 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {RISKS.map((risk, index) => (
            <TimelineAnimation
              key={risk.title}
              animationNum={3 + index}
              timelineRef={timelineRef}
              className="group relative overflow-hidden rounded-2xl border border-[var(--mk-line)] bg-[var(--mk-panel)] p-8 transition-colors hover:border-[var(--mk-accent)]"
            >
              {/* Low-opacity icon pattern. */}
              <div
                aria-hidden="true"
                className="pointer-events-none absolute -top-6 -right-8 opacity-[0.04] transition-opacity duration-300 group-hover:opacity-[0.09]"
              >
                <risk.icon className="size-40" strokeWidth={1} />
              </div>

              <article className="relative z-10">
                <div className="mb-6 grid size-8 place-items-center rounded-lg border border-[var(--mk-line)] bg-[var(--mk-raise)] transition-colors group-hover:border-[var(--mk-accent)] group-hover:bg-[var(--mk-accent)] group-hover:text-[var(--mk-accent-contrast)]">
                  <risk.icon className="size-4" />
                </div>
                <h3 className="mb-2 text-xs font-bold tracking-widest text-[var(--mk-muted)] uppercase">
                  {risk.tag}
                </h3>
                <p className="mb-4 text-lg leading-snug font-bold tracking-tight text-balance">
                  {risk.title}
                </p>
                <p className="text-sm leading-relaxed text-[var(--mk-muted)]">{risk.body}</p>
              </article>
            </TimelineAnimation>
          ))}
        </div>
      </div>
    </section>
  );
}
