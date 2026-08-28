"use client";

import type { Variants } from "motion/react";
import { type HTMLMotionProps, motion, useInView, useReducedMotion } from "motion/react";
import type React from "react";
import { useEffect, useState } from "react";

/**
 * Staggered scroll reveal, taken from the ui-layouts block set so the
 * marketing sections built on those blocks animate the way they were
 * designed to: a blur-and-fade keyed off one shared section ref, with each
 * child's delay derived from its `animationNum`.
 *
 * Three changes from the upstream component.
 *
 * It honours `prefers-reduced-motion` by rendering the visible state outright
 * rather than animating.
 *
 * The default delay step is 0.12s instead of 0.5s, which at eight children
 * meant the last one arrived four seconds after the first.
 *
 * And it carries the same safety net as this codebase's own `Reveal`: the
 * hidden state is `opacity: 0`, so if the observer never fires (a missed
 * intersection edge case, a stalled main thread, a browser without
 * IntersectionObserver) the upstream component leaves whole sections of real
 * content permanently invisible. A reveal effect must never be able to hide
 * the page, so after 1.5s it shows regardless.
 */

type TimelineContentProps<T extends keyof HTMLElementTagNameMap> = {
  children?: React.ReactNode;
  animationNum: number;
  className?: string;
  timelineRef: React.RefObject<HTMLElement | null>;
  as?: T;
  customVariants?: Variants;
  once?: boolean;
} & HTMLMotionProps<T>;

export const TimelineAnimation = <T extends keyof HTMLElementTagNameMap = "div">({
  children,
  animationNum,
  timelineRef,
  className,
  as,
  customVariants,
  once = true,
  ...props
}: TimelineContentProps<T>) => {
  const reduceMotion = useReducedMotion();

  const defaultSequenceVariants: Variants = {
    visible: (i: number) => ({
      filter: "blur(0px)",
      y: 0,
      opacity: 1,
      transition: { delay: i * 0.12, duration: 0.5 },
    }),
    hidden: { filter: "blur(12px)", y: 12, opacity: 0 },
  };

  const sequenceVariants = customVariants || defaultSequenceVariants;
  const isInView = useInView(timelineRef, { once });

  const [forceVisible, setForceVisible] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setForceVisible(true), 1500);
    return () => window.clearTimeout(timer);
  }, []);

  const MotionComponent = motion[as || "div"] as React.ElementType;

  if (reduceMotion) {
    const Plain = (as || "div") as React.ElementType;
    return (
      <Plain className={className} {...props}>
        {children}
      </Plain>
    );
  }

  return (
    <MotionComponent
      initial="hidden"
      animate={isInView || forceVisible ? "visible" : "hidden"}
      custom={animationNum}
      variants={sequenceVariants}
      className={className}
      {...props}
    >
      {children}
    </MotionComponent>
  );
};
