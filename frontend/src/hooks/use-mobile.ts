import * as React from "react";

const MOBILE_BREAKPOINT = 768;
const QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`;

/**
 * Whether the viewport is narrow enough that the sidebar becomes a drawer.
 *
 * Written against `useSyncExternalStore` rather than the effect-plus-setState
 * shape the component generator ships: a media query is an external store, and
 * subscribing to one by setting state inside an effect costs a second render
 * on every mount and trips this project's `react-hooks/set-state-in-effect`
 * rule. It also removes the `undefined` first pass, so the sidebar no longer
 * renders once as desktop before correcting itself on a phone.
 *
 * `getServerSnapshot` returns false because there is no viewport during SSR.
 * Desktop is the safe assumption: the drawer is opened by a control that is
 * itself hidden on wide screens, so guessing wide renders a static sidebar
 * that hydration immediately corrects, while guessing narrow would render a
 * closed drawer over the whole page.
 */
function subscribe(onChange: () => void): () => void {
  const mql = window.matchMedia(QUERY);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}

export function useIsMobile(): boolean {
  return React.useSyncExternalStore(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    () => false,
  );
}
