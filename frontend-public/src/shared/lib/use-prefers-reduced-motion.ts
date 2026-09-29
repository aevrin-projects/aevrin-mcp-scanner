import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void) {
  const media = window.matchMedia(QUERY);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

/**
 * `prefers-reduced-motion`, hydration-safe.
 *
 * motion's `useReducedMotion` answers from `matchMedia` on the client's very
 * first render, so a component whose *text* depends on it (the hero's
 * dashboard draws its counters at 1 instead of 0) renders differently from
 * the static HTML and React throws a hydration error (#418). This returns the
 * server's answer (false) while hydrating and the real one straight after,
 * and follows the setting if it changes mid-visit.
 */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    () => false,
  );
}
