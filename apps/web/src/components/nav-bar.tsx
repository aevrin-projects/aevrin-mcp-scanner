"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button, buttonVariants } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";

const HIDDEN_PATHS = ["/login", "/error"];
const AUTH_PREFIXES = ["/auth"];

export function NavBar({ email }: { email?: string | null }) {
  const pathname = usePathname();
  const router = useRouter();

  if (HIDDEN_PATHS.includes(pathname) || AUTH_PREFIXES.some((p) => pathname.startsWith(p))) {
    return null;
  }

  async function signOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  const signedIn = Boolean(email);

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        <Link href={signedIn ? "/dashboard" : "/"} className="flex items-center gap-2 font-semibold">
          <Image src="/logo.png" alt="" width={22} height={24} priority />
          <span>Aevrin</span>
        </Link>
        <nav className="flex items-center gap-5 text-sm text-muted-foreground">
          {signedIn ? (
            <>
              <Link href="/dashboard" className="hover:text-foreground">
                New scan
              </Link>
              <Link href="/settings/api-keys" className="hidden hover:text-foreground sm:inline">
                API keys
              </Link>
              <Link href="/settings/billing" className="hidden hover:text-foreground sm:inline">
                Billing
              </Link>
              <span className="hidden text-xs md:inline">{email}</span>
              <ThemeToggle />
              <Button variant="ghost" size="sm" onClick={signOut}>
                Sign out
              </Button>
            </>
          ) : (
            <>
              <Link href="/#product" className="hidden hover:text-foreground sm:inline">
                Product
              </Link>
              <Link href="/pricing" className="hover:text-foreground">
                Pricing
              </Link>
              <Link href="/docs" className="hover:text-foreground">
                Docs
              </Link>
              <a
                href="https://github.com/aevrin-projects/aevrin-mcp-scanner"
                target="_blank"
                rel="noreferrer"
                className="hidden hover:text-foreground sm:inline"
              >
                GitHub
              </a>
              <ThemeToggle />
              <Link href="/login" className={buttonVariants({ size: "sm" })}>
                Get started
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
