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

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur-sm">
      <div className="mx-auto grid h-[4.5rem] w-full max-w-[1600px] grid-cols-[auto_1fr_auto] items-center gap-3 px-4 sm:gap-6 sm:px-6 lg:px-10 xl:px-14">
        <Link
          href={signedIn ? "/dashboard" : "/"}
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
          <Link href="/pricing" className="hidden hover:text-foreground md:inline">
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
          <Link href={signedIn ? "/dashboard" : "/login"} className={buttonVariants({ size: "sm" })}>
            {signedIn ? "Open app" : "Sign in"}
          </Link>
        </div>
      </div>
    </header>
  );
}
