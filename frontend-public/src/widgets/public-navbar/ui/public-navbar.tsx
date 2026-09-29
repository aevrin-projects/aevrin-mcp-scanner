"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Menu, X } from "lucide-react";
import { ThemeToggle } from "@/features/theme";
import { cn } from "@/shared/lib/utils";

// The authenticated app lives on a different origin (DECISIONS.md ADR-011),
// so every auth-adjacent link here is necessarily cross-domain.
const LOGIN_HREF = "https://app.mcp.aevrin.net/login";
const DOCS_HREF = "https://docs.mcp.aevrin.net";

/** Past this many pixels the bar condenses into the floating pill. */
const SCROLL_THRESHOLD = 20;

function useNavLinks() {
  const pathname = usePathname();
  // A same-page fragment on the home page, so the browser scrolls instead of
  // re-navigating; from any other route it has to go through `/`.
  const pricingHref = pathname === "/" ? "#pricing" : "/#pricing";
  return [
    { label: "Pricing", href: pricingHref },
    { label: "Docs", href: DOCS_HREF },
    { label: "CLI", href: "/cli" },
    { label: "Status", href: "/status" },
  ];
}

/**
 * Folio's two-state navigation: transparent and wide at the top of the page,
 * then a narrower blurred pill with a hairline once the page moves. The state
 * change is a 300ms transition on width, radius, border and fill.
 *
 * Below 768px the links move into a menu panel. The previous bar had none, so
 * on a phone Pricing and Status were simply unreachable. The panel behaves
 * like a small modal: focus moves into it, Tab stays inside it, Escape and the
 * backdrop close it and return focus to the button, and the page behind it
 * does not scroll.
 */
export function PublicNavbar() {
  const links = useNavLinks();
  const pathname = usePathname();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const update = () => setScrolled(window.scrollY > SCROLL_THRESHOLD);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false);
    if (restoreFocus) buttonRef.current?.focus();
  }, []);

  // A route change (a link inside the panel) closes it.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.querySelector<HTMLElement>("a, button")?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close(true);
        return;
      }
      if (event.key !== "Tab") return;
      // The trap spans the menu button and the panel, so the button that
      // opened the menu stays reachable for closing it again.
      const focusable = [
        buttonRef.current,
        ...(panelRef.current?.querySelectorAll<HTMLElement>("a[href], button:not([disabled])") ?? []),
      ].filter((element): element is HTMLElement => element !== null);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      } else if (!focusable.includes(active as HTMLElement)) {
        event.preventDefault();
        first.focus();
      }
    };
    // The panel only exists below 768px; widening the window past that with
    // it open would otherwise leave the page scroll-locked behind nothing.
    const wide = window.matchMedia("(min-width: 48rem)");
    const onWide = () => {
      if (wide.matches) close(false);
    };

    document.addEventListener("keydown", onKeyDown);
    wide.addEventListener("change", onWide);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
      wide.removeEventListener("change", onWide);
    };
  }, [open, close]);

  const condensed = scrolled || open;

  return (
    <>
      <a
        href="#main"
        className="mk-btn mk-btn-solid fixed top-2 left-2 z-[60] -translate-y-24 focus-visible:translate-y-0"
      >
        Skip to content
      </a>

      {open ? (
        <div
          aria-hidden="true"
          className="fixed inset-0 z-40 bg-[var(--mk-bg)]/70 md:hidden"
          onClick={() => close(false)}
        />
      ) : null}

      <header className="fixed inset-x-0 top-0 z-50 px-2">
        <div
          className={cn(
            "mx-auto border transition-all duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] motion-reduce:transition-none",
            condensed
              ? "mt-2 max-w-4xl rounded-2xl border-[var(--mk-line)] bg-[var(--mk-bg)]/70 px-3 backdrop-blur-lg sm:px-4"
              : "mt-0 max-w-6xl rounded-none border-transparent bg-transparent px-2 sm:px-4 lg:px-12",
          )}
        >
          <nav
            aria-label="Primary"
            className={cn(
              "flex items-center justify-between gap-4 transition-[height] duration-300 motion-reduce:transition-none",
              condensed ? "h-14" : "h-[68px]",
            )}
          >
            <Link href="/" aria-label="Aevrin home" className="flex shrink-0 items-center gap-2.5 rounded-md">
              <Image src="/logo.png" alt="" width={22} height={24} priority />
              <span className="text-[15px] font-semibold tracking-[0.14em] text-[var(--mk-fg-strong)] uppercase">
                Aevrin
              </span>
            </Link>

            <ul className="hidden items-center gap-1 md:flex">
              {links.map((link) => (
                <li key={link.label}>
                  <Link
                    href={link.href}
                    aria-current={link.href === pathname ? "page" : undefined}
                    className="rounded-md px-3 py-2 text-sm text-[var(--mk-muted)] transition-colors duration-150 hover:text-[var(--mk-fg)] aria-[current=page]:text-[var(--mk-fg)]"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>

            <div className="flex items-center gap-2">
              <div className="hidden items-center gap-2 md:flex">
                <ThemeToggle />
                <Link href={LOGIN_HREF} className="mk-btn mk-btn-sm mk-btn-outline">
                  Sign in
                </Link>
                <Link href={LOGIN_HREF} className="mk-btn mk-btn-sm mk-btn-solid">
                  Start free
                </Link>
              </div>
              <button
                ref={buttonRef}
                type="button"
                className="mk-btn mk-btn-sm -mr-1 px-2 text-[var(--mk-fg)] hover:bg-[var(--mk-hover)] md:hidden"
                aria-expanded={open}
                aria-controls="mobile-menu"
                aria-label={open ? "Close menu" : "Open menu"}
                onClick={() => setOpen((value) => !value)}
              >
                {open ? <X className="size-5" aria-hidden="true" /> : <Menu className="size-5" aria-hidden="true" />}
              </button>
            </div>
          </nav>

          <div
            ref={panelRef}
            id="mobile-menu"
            hidden={!open}
            className="pb-3 md:hidden"
          >
            <div className="max-h-[calc(100dvh-5.5rem)] overflow-y-auto rounded-3xl border border-[var(--mk-line)] bg-[var(--mk-bg)] p-4 shadow-2xl shadow-black/20">
              <ul className="flex flex-col">
                {links.map((link) => (
                  <li key={link.label}>
                    <Link
                      href={link.href}
                      aria-current={link.href === pathname ? "page" : undefined}
                      onClick={() => close(false)}
                      className="block rounded-lg px-3 py-3 text-lg text-[var(--mk-muted)] transition-colors hover:bg-[var(--mk-hover)] hover:text-[var(--mk-fg)] aria-[current=page]:text-[var(--mk-fg)]"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
              <div className="mt-3 flex items-center justify-between border-t border-[var(--mk-line)] px-1 pt-4">
                <span className="text-sm text-[var(--mk-muted)]">Theme</span>
                <ThemeToggle />
              </div>
              <div className="mt-4 grid gap-2">
                <Link href={LOGIN_HREF} className="mk-btn mk-btn-outline w-full">
                  Sign in
                </Link>
                <Link href={LOGIN_HREF} className="mk-btn mk-btn-solid w-full">
                  Start free
                </Link>
              </div>
            </div>
          </div>
        </div>
      </header>
    </>
  );
}
