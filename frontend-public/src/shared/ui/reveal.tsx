"use client";

import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";
import { cn } from "@/shared/lib/utils";

/**
 * Fade and rise into view, once, the first time an element scrolls in.
 *
 * The rendered HTML is always the visible state. Only after mount, and only
 * for an element that is still below the fold, does script mark it hidden
 * (`data-reveal="hidden"`, styled in globals.css) and hand it to an
 * IntersectionObserver. So nothing a reader can already see ever blinks out,
 * and a page without script, a printout or a crawler gets every section.
 *
 * The previous version started hidden in the server HTML and used a 1.5s
 * timer as a safety net, which meant sections further down were usually
 * revealed by the timer, off screen, before anyone scrolled to them.
 *
 * Transform and opacity only, and no-op under prefers-reduced-motion (the CSS
 * forces the visible state too, in case the preference changes mid-visit).
 */
export function Reveal({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  /** Stagger, in milliseconds, applied when the element enters. */
  delay?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (typeof IntersectionObserver === "undefined") return;
    if (element.getBoundingClientRect().top < window.innerHeight) return;

    element.dataset.reveal = "hidden";
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        element.dataset.reveal = "shown";
        observer.disconnect();
      },
      { rootMargin: "0px 0px -8% 0px" },
    );
    observer.observe(element);
    return () => {
      observer.disconnect();
      element.dataset.reveal = "shown";
    };
  }, []);

  return (
    <div
      ref={ref}
      className={cn("mk-reveal", className)}
      style={delay ? ({ "--reveal-delay": `${delay}ms` } as CSSProperties) : undefined}
    >
      {children}
    </div>
  );
}
