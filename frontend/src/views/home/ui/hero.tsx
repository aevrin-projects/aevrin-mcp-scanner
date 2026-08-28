"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import {
  motion,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
  type MotionValue,
} from "motion/react";
import {
  ArrowRight,
  Boxes,
  Eye,
  KeyRound,
  PackageOpen,
  TerminalSquare,
  Waypoints,
} from "lucide-react";
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
 * The chips are labelled with the OWASP MCP categories a scan checks. Two are
 * drawn in severity colours and the rest are neutral, because in this product a
 * red chip has to keep meaning "critical" rather than "decorative".
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
    label: "Rug pulls",
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
  const reduceMotion = useReducedMotion();
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
    <section
      ref={sectionRef}
      className="relative overflow-hidden px-6 pt-16 pb-14 lg:pt-24"
    >
      <div className="mx-auto max-w-6xl">
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
              className="mk-lede mx-auto mt-6 max-w-xl"
            >
              Aevrin runs ten open-source security scanners over a repository, a live server or a
              pasted config, then tells you plainly what it found and, just as plainly, what it
              could not check.
            </TimelineAnimation>

            <TimelineAnimation
              animationNum={2}
              timelineRef={timelineRef}
              className="mt-9 flex flex-wrap items-center justify-center gap-3"
            >
              <Link href={primaryHref} className="mk-btn mk-btn-solid">
                {signedIn ? "Open dashboard" : "Start scanning free"}
                <ArrowRight className="size-4" />
              </Link>
              <Link href="https://docs.mcp.aevrin.net" className="mk-btn mk-btn-ghost">
                Read the docs
              </Link>
            </TimelineAnimation>

            <TimelineAnimation
              animationNum={3}
              timelineRef={timelineRef}
              as="p"
              className="mt-4 text-[13px]"
              style={{ color: "var(--mk-muted)" }}
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
