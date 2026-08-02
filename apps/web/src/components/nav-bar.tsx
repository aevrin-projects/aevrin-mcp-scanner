"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button, buttonVariants } from "@/components/ui/button";
import { ShieldCheck } from "lucide-react";

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
    <header className="border-b border-border">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
        <Link href={signedIn ? "/dashboard" : "/"} className="flex items-center gap-2 font-medium">
          <ShieldCheck className="size-5" />
          <span>Aevrin</span>
        </Link>
        <nav className="flex items-center gap-4 text-sm text-muted-foreground">
          {signedIn ? (
            <>
              <Link href="/dashboard" className="hover:text-foreground">
                New scan
              </Link>
              <Link href="/settings/api-keys" className="hover:text-foreground">
                API keys
              </Link>
              <Link href="/settings/billing" className="hover:text-foreground">
                Billing
              </Link>
              <span className="text-xs">{email}</span>
              <Button variant="ghost" size="sm" onClick={signOut}>
                Sign out
              </Button>
            </>
          ) : (
            <>
              <Link href="/pricing" className="hover:text-foreground">
                Pricing
              </Link>
              <Link href="/docs" className="hover:text-foreground">
                Docs
              </Link>
              <Link href="/login" className={buttonVariants({ size: "sm" })}>
                Sign in
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
