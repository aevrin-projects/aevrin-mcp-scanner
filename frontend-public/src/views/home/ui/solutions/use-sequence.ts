"use client";

import { useCallback, useEffect, useRef, useState } from "react";

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * A one-shot, time-scheduled walk through a mockup's states.
 *
 * The server render, and every render without JavaScript, is the final
 * state: fully informative, never an empty frame waiting on a script. The
 * sequence is only armed when the element starts completely off screen, so
 * it cannot blank something the reader is already looking at, and it plays
 * once when a third of the element is visible. Under reduced motion it never
 * leaves the final state. Nothing here loops; `inView` exists so the one
 * ambient effect (a caret) can stop while the mockup is off screen.
 *
 * `schedule` holds the millisecond offset of each step and must be a stable
 * (module-level) array.
 */
export function useSequence<T extends Element>(schedule: readonly number[]) {
  const ref = useRef<T>(null);
  const final = schedule.length;
  const [step, setStep] = useState(final);
  const [inView, setInView] = useState(false);
  const timers = useRef<number[]>([]);
  const armed = useRef(false);

  const clearTimers = useCallback(() => {
    for (const id of timers.current) window.clearTimeout(id);
    timers.current = [];
  }, []);

  const play = useCallback(() => {
    clearTimers();
    if (prefersReducedMotion()) {
      setStep(final);
      return;
    }
    setStep(0);
    schedule.forEach((at, index) => {
      timers.current.push(window.setTimeout(() => setStep(index + 1), at));
    });
  }, [clearTimers, final, schedule]);

  useEffect(() => {
    const element = ref.current;
    if (!element || typeof IntersectionObserver === "undefined") return;

    let first = true;
    const observer = new IntersectionObserver(
      ([entry]) => {
        const visible = entry.intersectionRatio >= 0.35;
        setInView(entry.isIntersecting);
        if (first) {
          first = false;
          if (!entry.isIntersecting && !prefersReducedMotion()) {
            armed.current = true;
            setStep(0);
          }
          return;
        }
        if (visible && armed.current) {
          armed.current = false;
          play();
        }
      },
      { threshold: [0, 0.35] },
    );
    observer.observe(element);
    return () => {
      observer.disconnect();
      clearTimers();
    };
  }, [clearTimers, play]);

  return { ref, step, final, inView, replay: play };
}

/** Plays a CSS entrance once, with the same arming rule as `useSequence`. */
export function useEntrance<T extends Element>() {
  const ref = useRef<T>(null);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element || typeof IntersectionObserver === "undefined") return;

    let first = true;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (first) {
          first = false;
          if (!entry.isIntersecting && !prefersReducedMotion()) setHidden(true);
          else observer.disconnect();
          return;
        }
        if (entry.intersectionRatio > 0.12) {
          setHidden(false);
          observer.disconnect();
        }
      },
      { threshold: [0, 0.12] },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return { ref, hidden };
}
