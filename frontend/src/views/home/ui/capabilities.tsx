"use client";

import Link from "next/link";
import { useRef } from "react";
import {
  ArrowRight,
  FileText,
  GitBranch,
  Server,
  Sparkles,
  Users,
  Waypoints,
} from "lucide-react";
import { BrandIcon } from "@/shared/ui/brand-icon";
import { TimelineAnimation } from "@/shared/ui/timeline-animation";

/**
 * Capabilities, in the reference block set's feature-card idiom: a soft panel
 * holding an inset surface, with the label and copy sitting underneath rather
 * than inside the card.
 *
 * Everything listed here exists in the product today. The three claims this
 * section used to carry, an org-wide hook policy console, SSO, and
 * bring-your-own model key, are gone: two were removed from the product and
 * the third never shipped.
 */

const FEATURES = [
  {
    icon: Sparkles,
    title: "Agent posture",
    body: "Scan the coding agents already on your machine. Aevrin reads what Claude Code and Codex are configured to do, and grades what that exposes.",
    href: "/docs",
    // Inset preview: what the agent scan lists back. The two agents carry
    // their real marks; the counts are plain text.
    preview: [
      { label: "Claude Code", brand: "claude" as const },
      { label: "Codex", brand: "openai" as const },
      { label: "14 MCP servers" },
      { label: "6 skills" },
    ],
  },
  {
    icon: Server,
    title: "MCP inventory",
    body: "Every server you have connected, in one list, each graded A to D so the risky one is obvious without opening it.",
    href: "/docs",
    preview: [
      { label: "A  Low risk" },
      { label: "B  Review" },
      { label: "C  Caution" },
      { label: "D  Do not install" },
    ],
  },
  {
    icon: Waypoints,
    title: "Attack paths",
    body: "Where a poisoned tool description, an over-scoped token and a shell-reaching argument line up into one route through your setup.",
    href: "/docs",
    preview: [
      { label: "Tool description" },
      { label: "to credential" },
      { label: "to shell" },
      { label: "to host" },
    ],
  },
  {
    icon: GitBranch,
    title: "Hooks and CI",
    body: "A pre-install hook for your agent, and an exit code your pipeline can branch on. An incomplete scan fails closed instead of passing quietly.",
    href: "/docs",
    preview: [
      { label: "exit 0  clean" },
      { label: "exit 1  findings" },
      { label: "exit 2  error" },
      { label: "exit 3  incomplete" },
    ],
  },
  {
    icon: Users,
    title: "Shared workspaces",
    body: "Invite colleagues by email, and define the roles yourself: choose exactly what each one is allowed to do. Scans, agents and findings are shared.",
    href: "/pricing",
    preview: [
      { label: "Owner" },
      { label: "Roles you define" },
      { label: "Invite by email" },
      { label: "Seats you buy" },
    ],
  },
  {
    icon: FileText,
    title: "Exportable report",
    body: "A self-contained document that prints cleanly, states a conclusion rather than only a score, and survives being read by someone who has never seen the dashboard.",
    href: "/docs",
    preview: [
      { label: "Verdict" },
      { label: "Findings" },
      { label: "Coverage" },
      { label: "Limitations" },
    ],
  },
];

export function Capabilities() {
  const timelineRef = useRef<HTMLDivElement>(null);

  return (
    <section
      ref={timelineRef}
      className="border-y px-6 py-20 lg:py-28"
      style={{ borderColor: "var(--mk-line)", background: "var(--mk-panel)" }}
    >
      <div className="mx-auto max-w-6xl">
        <div className="max-w-2xl">
          <TimelineAnimation
            animationNum={0}
            timelineRef={timelineRef}
            as="p"
            className="mk-mono"
          >
            The platform
          </TimelineAnimation>
          <TimelineAnimation
            animationNum={1}
            timelineRef={timelineRef}
            as="h2"
            className="mk-h2 mt-4"
          >
            The whole surface your agent touches.
          </TimelineAnimation>
          <TimelineAnimation
            animationNum={2}
            timelineRef={timelineRef}
            as="p"
            className="mk-lede mt-5"
          >
            A server is one part of it. The agent that installed it, the
            credentials it inherited and the route between them are the rest.
          </TimelineAnimation>
        </div>

        <div className="mt-14 grid gap-x-6 gap-y-12 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature, index) => (
            <TimelineAnimation
              key={feature.title}
              animationNum={3 + index}
              timelineRef={timelineRef}
              className="flex flex-col"
            >
              {/* Soft panel holding an inset surface: the reference's card shape. */}
              <div
                className="aspect-[16/10] overflow-hidden rounded-xl p-5"
                style={{
                  background: "var(--mk-raise)",
                  border: "1px solid var(--mk-line)",
                }}
              >
                <div
                  className="flex h-full translate-y-4 flex-col gap-2 rounded-lg p-4"
                  style={{
                    background: "var(--mk-panel)",
                    border: "1px solid var(--mk-line-soft)",
                  }}
                >
                  <feature.icon className="size-4 shrink-0" />
                  {feature.preview.map((line) => (
                    <p
                      key={line.label}
                      className="flex items-center gap-2 truncate font-mono text-[11.5px]"
                      style={{ color: "var(--mk-muted)" }}
                    >
                      {"brand" in line && line.brand ? (
                        <BrandIcon name={line.brand} className="size-3.5" />
                      ) : null}
                      {line.label}
                    </p>
                  ))}
                </div>
              </div>

              <h3 className="mk-h3 mt-5">{feature.title}</h3>
              <p
                className="mt-2.5 text-[14px] leading-relaxed"
                style={{ color: "var(--mk-muted)" }}
              >
                {feature.body}
              </p>
              <Link
                href={feature.href}
                className="mt-3.5 inline-flex items-center gap-1.5 text-[13.5px] font-semibold hover:opacity-70"
              >
                Learn more
                <ArrowRight className="size-3.5" />
              </Link>
            </TimelineAnimation>
          ))}
        </div>
      </div>
    </section>
  );
}
