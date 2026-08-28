"use client";

import Image from "next/image";
import Link from "next/link";
import { ThemeToggle } from "@/features/theme";
import { buttonVariants } from "@/shared/ui/button";

// The authenticated app (dashboard, login, everything requiring a session)
// lives on a different origin -- see DECISIONS.md ADR-011 for why this app
// is separate at all. Every auth-adjacent link here is necessarily
// cross-domain, unlike the same component's copy in `frontend/`.
const APP_ORIGIN = "https://app.mcp.aevrin.net";

export function PublicNavbar({ signedIn }: { signedIn: boolean }) {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur-sm">
      <div className="mx-auto grid h-[4.5rem] w-full max-w-[1600px] grid-cols-[auto_1fr_auto] items-center gap-3 px-4 sm:gap-6 sm:px-6 lg:px-10 xl:px-14">
        <Link
          href={signedIn ? `${APP_ORIGIN}/dashboard` : "/"}
          aria-label={signedIn ? "Open Aevrin dashboard" : "Aevrin home"}
          className="flex items-center gap-3 font-semibold"
        >
          <Image src="/logo.png" alt="" width={24} height={26} priority />
          <span className="hidden text-base tracking-[0.14em] text-foreground uppercase min-[430px]:inline sm:text-lg">
            Aevrin
          </span>
        </Link>

        <nav className="flex min-w-0 items-center justify-center gap-3 text-sm text-muted-foreground sm:gap-6" aria-label="Primary navigation">
          <Link href="/" className="hover:text-foreground">
            Home
          </Link>
          <Link href={`${APP_ORIGIN}/pricing`} className="hidden hover:text-foreground md:inline">
            Pricing
          </Link>
          <Link href="https://docs.mcp.aevrin.net" className="hover:text-foreground">
            Docs
          </Link>
          <Link href="/status" className="hidden hover:text-foreground lg:inline">
            Status
          </Link>
        </nav>

        <div className="flex items-center justify-end gap-2 sm:gap-3">
          <ThemeToggle />
          <Link
            href={signedIn ? `${APP_ORIGIN}/dashboard` : `${APP_ORIGIN}/login`}
            className={buttonVariants({ size: "sm" })}
          >
            {signedIn ? "Open app" : "Sign in"}
          </Link>
        </div>
      </div>
    </header>
  );
}
