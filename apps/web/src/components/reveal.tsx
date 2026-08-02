"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

// Subtle fade + slide-up on scroll into view — matches aevrin.net's reveal
// pattern. Deliberately small distance and short duration; this is meant to
// be felt, not noticed. Respects prefers-reduced-motion by skipping the
// initial hidden state entirely rather than firing the animation anyway.
export function Reveal({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [skipAnimation] = useState(prefersReducedMotion);
  const [visible, setVisible] = useState(skipAnimation);

  useEffect(() => {
    if (skipAnimation) return;
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.1, rootMargin: "0px 0px -40px 0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [skipAnimation]);

  return (
    <div
      ref={ref}
      className={cn(!skipAnimation && "transition-all duration-700 ease-out", className)}
      style={
        skipAnimation
          ? undefined
          : {
              opacity: visible ? 1 : 0,
              transform: visible ? "translateY(0)" : "translateY(16px)",
              transitionDelay: `${delay}ms`,
            }
      }
    >
      {children}
    </div>
  );
}
