"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import {
  motion,
  useMotionValueEvent,
  useScroll,
  useSpring,
  useTransform,
  type MotionValue,
} from "motion/react";
import {
  ArrowRight,
  Boxes,
  ChevronRight,
  Eye,
  KeyRound,
  PackageOpen,
  TerminalSquare,
  Waypoints,
} from "lucide-react";
import { usePrefersReducedMotion } from "@/shared/lib/use-prefers-reduced-motion";
import { TimelineAnimation } from "@/shared/ui/timeline-animation";
import { DashboardPreview } from "@/widgets/dashboard-preview";

/**
 * Hero: a centred display-serif headline with capability chips scattered into
 * the whitespace either side of it, one square high-contrast action, and the
 * product itself directly underneath.
 *
 * The chips are scroll-linked. As the page moves they drift down and inward
 * and slide *under* the dashboard, which sits on a higher stacking layer with
 * an opaque background and therefore occludes them; scrolling back up runs the
 * whole thing in reverse, because the motion is driven by scroll position
 * rather than by a one-way animation. A spring smooths the raw scroll value so
 * a trackpad flick reads as momentum instead of a jump.
 *
 * The dashboard draws itself on the same scroll value. Its gauge, donut, bars
 * and every number are derived from a single 0-to-1 reveal, so the counters
 * climb and the charts fill while the chips are on their way down, and all of
 * it lands together as the last one submerges. Scrolling back up rewinds the
 * charts too, because they are reading scroll position rather than playing an
 * animation.
 *
 * The chips are labelled with the OWASP MCP categories a scan checks and the
 * two agent views. Two are drawn in severity colours and the rest are neutral,
 * because in this product a red chip has to keep meaning "critical" rather than
 * "decorative". "Rug pulls" was replaced by "Supply chain": Aevrin no longer
 * tracks tool drift between scans, while six rules map to MCP07.
 *
 * Styling follows Folio (serif headline, 6px buttons, dashed guide frame); the
 * scroll, spring, chips, reveal and z-order below are unchanged.
 */

const CHIPS = [
  {
    label: "Tool poisoning",
    icon: Eye,
    at: "left-[2%] top-[10%]",
    tone: "bg-severity-medium/15 text-severity-medium",
    // Direction of travel as the chip submerges. Left-hand chips sweep right,
    // right-hand chips sweep left, and all of them fall toward the dashboard.
    drift: { x: 150, rotate: -6 },
  },
  {
    label: "Token mismanagement",
    icon: KeyRound,
    at: "left-[1%] top-[44%]",
    tone: "bg-brand/12 text-brand-text",
    drift: { x: 120, rotate: 4 },
  },
  {
    label: "Command injection",
    icon: TerminalSquare,
    at: "left-[1%] bottom-[16%]",
    tone: "bg-severity-critical/12 text-severity-critical",
    drift: { x: 170, rotate: -3 },
  },
  {
    label: "Supply chain",
    icon: PackageOpen,
    at: "right-[3%] top-[12%]",
    tone: "bg-severity-high/14 text-severity-high",
    drift: { x: -150, rotate: 6 },
  },
  {
    label: "Agent posture",
    icon: Boxes,
    at: "right-[1%] top-[44%]",
    tone: "bg-brand/12 text-brand-text",
    drift: { x: -120, rotate: -4 },
  },
  {
    label: "Attack paths",
    icon: Waypoints,
    at: "right-[2%] bottom-[18%]",
    tone: "bg-severity-low/14 text-severity-low",
    drift: { x: -170, rotate: 3 },
  },
];

/** How far down a chip travels before the dashboard covers it. */
const SUBMERGE_DISTANCE = 560;

function Chip({
  chip,
  progress,
  index,
  timelineRef,
  reduceMotion,
}: {
  chip: (typeof CHIPS)[number];
  progress: MotionValue<number>;
  index: number;
  timelineRef: React.RefObject<HTMLElement | null>;
  reduceMotion: boolean | null;
}) {
  // Chips further from the centre start a beat later, so the group collapses
  // inward rather than moving as one rigid block.
  const stagger = (index % 3) * 0.05;
  const y = useTransform(progress, [stagger, 1], [0, SUBMERGE_DISTANCE]);
  const x = useTransform(progress, [stagger, 1], [0, chip.drift.x]);
  const rotate = useTransform(progress, [stagger, 1], [0, chip.drift.rotate]);
  const scale = useTransform(progress, [stagger, 1], [1, 0.72]);
  // Only the last stretch fades, so the chip is genuinely occluded by the
  // dashboard for most of the trip rather than dissolving in mid-air.
  const opacity = useTransform(progress, [0, 0.82, 1], [1, 1, 0]);

  if (reduceMotion) {
    return (
      <div className={`absolute ${chip.at}`}>
        <span className={`mk-chip ${chip.tone}`}>
          <chip.icon className="size-3.5" />
          {chip.label}
        </span>
      </div>
    );
  }

  return (
    <TimelineAnimation
      animationNum={index + 2}
      timelineRef={timelineRef}
      className={`absolute ${chip.at}`}
    >
      <motion.span
        className={`mk-chip ${chip.tone}`}
        style={{ x, y, rotate, scale, opacity }}
      >
        <chip.icon className="size-3.5" />
        {chip.label}
      </motion.span>
    </TimelineAnimation>
  );
}

export function Hero({ primaryHref, signedIn }: { primaryHref: string; signedIn: boolean }) {
  const timelineRef = useRef<HTMLDivElement>(null);
  const sectionRef = useRef<HTMLElement>(null);
  // Hydration-safe: the dashboard's counters are text, and drawing them at 1
  // on the client's first render (reduced motion) while the static HTML has 0
  // was a hydration error.
  const reduceMotion = usePrefersReducedMotion();
  // Quantised so the dashboard re-renders a bounded number of times across the
  // whole scroll rather than on every frame. 60 steps is finer than the eye
  // resolves on a counter and cheap enough to be free.
  const [reveal, setReveal] = useState(0);

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end start"],
  });

  // The submerge is finished well before the hero has fully scrolled away, so
  // the raw progress is remapped onto the first stretch of it.
  const submerge = useTransform(scrollYProgress, [0, 0.42], [0, 1]);
  const smoothed = useSpring(submerge, { stiffness: 90, damping: 24, mass: 0.4 });

  // The dashboard finishes drawing itself as the last chip goes under, so the
  // reveal runs slightly ahead of the submerge and is eased rather than linear.
  useMotionValueEvent(smoothed, "change", (value) => {
    const eased = Math.min(1, Math.max(0, value / 0.9));
    const step = Math.round(eased * 60) / 60;
    setReveal((current) => (current === step ? current : step));
  });

  return (
    <section ref={sectionRef} className="relative overflow-hidden pt-14 pb-16 sm:pt-20 lg:pt-24 lg:pb-24">
      {/* Folio's guide frame: a dashed 1280px column running down the hero.
          Decorative, and dropped on phones where it would sit on the text. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 left-1/2 hidden w-full max-w-7xl -translate-x-1/2 border-x border-dashed border-[var(--mk-line)] sm:block"
      />
      {/* Dot-grid ground behind the dashboard, faded at every edge. Below the
          chips in paint order, so it never covers them. */}
      <div
        aria-hidden="true"
        className="mk-dots pointer-events-none absolute inset-x-0 bottom-0 h-[70%] [mask-image:radial-gradient(ellipse_60%_55%_at_50%_45%,black,transparent)]"
      />

      <div className="mk-container relative max-w-6xl">
        {/* The scatter is anchored to the copy block alone. Hidden below xl,
            where there is no margin to scatter into and the chips would just
            crowd the headline. */}
        <div className="relative">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 z-0 hidden xl:block"
          >
            {CHIPS.map((chip, index) => (
              <Chip
                key={chip.label}
                chip={chip}
                index={index}
                progress={smoothed}
                timelineRef={timelineRef}
                reduceMotion={reduceMotion}
              />
            ))}
          </div>

          <div ref={timelineRef} className="relative z-10 mx-auto max-w-3xl text-center">
            <TimelineAnimation animationNum={0} timelineRef={timelineRef} className="mb-7 flex justify-center">
              <Link
                href="https://docs.mcp.aevrin.net/agents"
                className="group relative inline-flex max-w-full overflow-hidden rounded-full p-px"
              >
                <span aria-hidden="true" className="mk-ring-spin" />
                <span className="relative inline-flex h-8 min-w-0 items-center gap-1.5 rounded-full border border-[var(--mk-line)] bg-[var(--mk-bg)] px-4 text-[13px] font-medium text-[var(--mk-fg)] sm:text-sm">
                  <span className="truncate">Search the Aevrin Registry from Claude Code</span>
                  <ChevronRight
                    className="size-3.5 shrink-0 text-[var(--mk-muted)] transition-transform duration-150 group-hover:translate-x-0.5"
                    aria-hidden="true"
                  />
                </span>
              </Link>
            </TimelineAnimation>

            <TimelineAnimation
              animationNum={0}
              timelineRef={timelineRef}
              as="h1"
              className="mk-display"
            >
              Know what an MCP server can do before you install it.
            </TimelineAnimation>

            <TimelineAnimation
              animationNum={1}
              timelineRef={timelineRef}
              as="p"
              className="mk-lede mx-auto mt-6 max-w-2xl"
            >
              Aevrin starts an MCP server in a sandbox, reads every tool it declares, and grades
              what it could do, from A to F. When a check cannot finish, the report says so
              instead of calling it clean.
            </TimelineAnimation>

            <TimelineAnimation
              animationNum={2}
              timelineRef={timelineRef}
              className="mt-8 flex flex-wrap items-center justify-center gap-3"
            >
              <Link href={primaryHref} className="mk-btn mk-btn-solid">
                {signedIn ? "Open dashboard" : "Start scanning free"}
                <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
              <Link href="https://docs.mcp.aevrin.net" className="mk-btn mk-btn-outline">
                Read the docs
              </Link>
            </TimelineAnimation>

            <TimelineAnimation
              animationNum={3}
              timelineRef={timelineRef}
              as="p"
              className="mt-4 text-[13px] text-[var(--mk-muted)]"
            >
              Free plan, no card. Five CLI scans a month.
            </TimelineAnimation>
          </div>
        </div>

        {/* Above the chips, and opaque, which is what makes them submerge
            rather than pass across it. */}
        <TimelineAnimation
          animationNum={4}
          timelineRef={timelineRef}
          className="relative z-20 mt-14 lg:mt-20"
        >
          <DashboardPreview reveal={reduceMotion ? 1 : reveal} />
        </TimelineAnimation>
      </div>
    </section>
  );
}
