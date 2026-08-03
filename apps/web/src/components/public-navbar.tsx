"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/theme-toggle";
import { buttonVariants } from "@/components/ui/button";

const AUTH_PREFIXES = ["/auth"];

export function PublicNavbar({ signedIn }: { signedIn: boolean }) {
  const pathname = usePathname();

  if (AUTH_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return null;
  }

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur-sm">
      <div className="flex h-[4.5rem] w-full items-center justify-between px-6 lg:px-10 xl:px-14">
        <Link href={signedIn ? "/dashboard" : "/"} className="flex items-center gap-3 font-semibold">
          <Image src="/logo.png" alt="" width={24} height={26} priority />
          <span className="text-base tracking-[0.14em] text-foreground uppercase sm:text-lg">
            Aevrin
          </span>
        </Link>

        <nav className="flex items-center gap-5 text-sm text-muted-foreground">
          <Link href="/pricing" className="hidden hover:text-foreground sm:inline">
            Pricing
          </Link>
          <Link href="/docs" className="hover:text-foreground">
            Docs
          </Link>
          <ThemeToggle />
          <Link href={signedIn ? "/dashboard" : "/login"} className={buttonVariants({ size: "sm" })}>
            {signedIn ? "Open app" : "Get started"}
          </Link>
        </nav>
      </div>
    </header>
  );
}
