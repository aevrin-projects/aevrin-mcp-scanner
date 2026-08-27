"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/features/theme";
import { buttonVariants } from "@/shared/ui/button";

const AUTH_PREFIXES = ["/auth"];

export function PublicNavbar({ signedIn }: { signedIn: boolean }) {
  const pathname = usePathname();

  if (AUTH_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return null;
  }

  // The docs section itself runs edge-to-edge (fumadocs' own sidebar/TOC
  // grid, not this max-width band), cap the nav here too so its logo and
  // links line up with that content instead of sitting inset above it.
  const isDocsRoute = pathname.startsWith("/docs");

  // The landing page carries its own light palette, and the shared header
  // reads from the app's dark-first tokens, so on that one route it arrived
  // as a black band above a white hero. Scoped to "/" rather than solved by
  // changing the tokens, because every other page still wants the app's.
  const isMarketing = pathname === "/";

  return (
    <header
      className={
        isMarketing
          ? "marketing sticky top-0 z-40 border-b border-[color:var(--mk-line)] bg-white/85 backdrop-blur-sm"
          : "sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur-sm"
      }
    >
      <div
        className={
          isDocsRoute
            ? "grid h-[4.5rem] w-full grid-cols-[auto_1fr_auto] items-center gap-3 px-4 sm:gap-6"
            : "mx-auto grid h-[4.5rem] w-full max-w-[1600px] grid-cols-[auto_1fr_auto] items-center gap-3 px-4 sm:gap-6 sm:px-6 lg:px-10 xl:px-14"
        }
      >
        <Link
          href={signedIn ? "/dashboard" : "/"}
          aria-label={signedIn ? "Open Aevrin dashboard" : "Aevrin home"}
          className="flex items-center gap-3 font-semibold"
        >
          <Image src="/logo.png" alt="" width={24} height={26} priority />
          <span
            className={`hidden text-base tracking-[0.14em] uppercase min-[430px]:inline sm:text-lg ${
              isMarketing ? "text-[color:var(--mk-ink)]" : "text-foreground"
            }`}
          >
            Aevrin
          </span>
        </Link>

        <nav
          className={`flex min-w-0 items-center justify-center gap-3 text-sm sm:gap-6 ${
            isMarketing ? "text-[color:var(--mk-ink)]/70" : "text-muted-foreground"
          }`}
          aria-label="Primary navigation"
        >
          <Link href="/" className={isMarketing ? "hover:text-[color:var(--mk-ink)]" : "hover:text-foreground"}>
            Home
          </Link>
          <Link href="/pricing" className={isMarketing ? "hidden hover:text-[color:var(--mk-ink)] md:inline" : "hidden hover:text-foreground md:inline"}>
            Pricing
          </Link>
          <Link href="/docs" className={isMarketing ? "hover:text-[color:var(--mk-ink)]" : "hover:text-foreground"}>
            Docs
          </Link>
          <Link href="/status" className={isMarketing ? "hidden hover:text-[color:var(--mk-ink)] lg:inline" : "hidden hover:text-foreground lg:inline"}>
            Status
          </Link>
        </nav>

        <div className="flex items-center justify-end gap-2 sm:gap-3">
          {isMarketing ? null : <ThemeToggle />}
          <Link
            href={signedIn ? "/dashboard" : "/login"}
            className={
              isMarketing
                ? "inline-flex h-9 items-center rounded-[4px] bg-[color:var(--mk-accent)] px-4 text-sm font-medium text-white transition-opacity hover:opacity-90"
                : buttonVariants({ size: "sm" })
            }
          >
            {signedIn ? "Open app" : "Sign in"}
          </Link>
        </div>
      </div>
    </header>
  );
}
