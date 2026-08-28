"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { BookOpen, ChevronDown, LogOut, Menu, MoonStar } from "lucide-react";
import { ThemeToggle } from "@/features/theme";
import { billingApi } from "@/entities/billing";
import { Button } from "@/shared/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/shared/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/ui/dropdown-menu";
import { SidebarNav } from "./sidebar-nav";

function accountMonogram(email: string) {
  const seed = email.split("@")[0]?.replace(/[^a-zA-Z0-9]/g, "") ?? "";
  return seed.slice(0, 2).toUpperCase() || "AV";
}

/**
 * A left sidebar rather than a top row of tabs. The product grew past what a
 * single horizontal row can carry without becoming a scroll, and grouping
 * ("AI security", "Scanning", "Automation") is what keeps a growing list
 * navigable: a flat row of nine tabs reads as nine buttons and nothing else.
 *
 * 15rem wide and no wider. The pages beside it are dense tables, and every
 * column of chrome is a column those tables do not get.
 */
export function AuthenticatedAppShell({
  children,
  email,
  onSignOut,
}: {
  children: React.ReactNode;
  email: string;
  onSignOut: () => Promise<void>;
}) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [tier, setTier] = useState<string | null>(null);
  const monogram = accountMonogram(email);

  // Best-effort: the plan badge is contextual, so a failed lookup just hides
  // it rather than surfacing an error on every authenticated page.
  useEffect(() => {
    let cancelled = false;
    billingApi
      .getSubscription()
      .then((subscription) => {
        if (!cancelled) setTier(subscription.effective_tier);
      })
      .catch(() => {
        if (!cancelled) setTier(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex min-h-screen bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-sm"
      >
        Skip to content
      </a>

      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-border bg-card md:flex">
        <div className="flex h-16 shrink-0 items-center border-b border-border px-5">
          <Link href="/dashboard" className="flex items-center gap-2 font-semibold">
            <Image src="/logo.png" alt="" width={20} height={22} priority />
            <span className="tracking-[0.12em] uppercase">Aevrin</span>
          </Link>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <SidebarNav pathname={pathname} />
        </div>
        {tier ? (
          <div className="shrink-0 border-t border-border p-3">
            <Link
              href="/settings/billing"
              className="flex items-center justify-between rounded-md px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
            >
              <span>Plan</span>
              <span className="font-medium capitalize">{tier}</span>
            </Link>
          </div>
        ) : null}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 border-b border-border bg-card/95 backdrop-blur">
          <div className="flex h-16 items-center gap-3 px-4 sm:px-6">
            <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
              <DialogTrigger
                render={
                  <Button variant="outline" size="icon-sm" aria-label="Open navigation" className="md:hidden" />
                }
              >
                <Menu className="size-4" />
              </DialogTrigger>
              <DialogContent className="top-0 left-0 flex h-full max-w-[300px] translate-x-0 translate-y-0 flex-col items-stretch gap-0 rounded-none border-r border-border p-0">
                <DialogHeader className="shrink-0 border-b border-border px-5 py-4">
                  <DialogTitle className="flex items-center gap-3">
                    <Image src="/logo.png" alt="" width={22} height={24} />
                    Aevrin
                  </DialogTitle>
                </DialogHeader>
                <div className="min-h-0 flex-1 overflow-y-auto p-3">
                  <SidebarNav pathname={pathname} onNavigate={() => setMobileOpen(false)} />
                </div>
              </DialogContent>
            </Dialog>

            <Link href="/dashboard" className="flex items-center gap-2 font-semibold md:hidden">
              <Image src="/logo.png" alt="" width={20} height={22} />
              <span className="tracking-[0.12em] uppercase">Aevrin</span>
            </Link>

            <div className="ms-auto flex items-center gap-2">
              <Button
                nativeButton={false}
                render={<Link href="/scans/new" />}
                size="sm"
                className="hidden sm:inline-flex"
              >
                New scan
              </Button>
              <ThemeToggle />
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-10 rounded-full px-1.5 hover:bg-muted/80"
                      aria-label="Open account menu"
                    />
                  }
                >
                  <span className="flex size-8 items-center justify-center rounded-md bg-muted text-xs font-semibold tracking-[0.08em] ring-1 ring-border ring-inset">
                    {monogram}
                  </span>
                  <ChevronDown className="size-4 text-muted-foreground" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-64">
                  <DropdownMenuGroup>
                    <div className="px-2 py-1.5">
                      <p className="subheader">Account</p>
                      <p className="mt-1 truncate text-sm">{email}</p>
                    </div>
                  </DropdownMenuGroup>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem>
                    <Link href="https://docs.mcp.aevrin.net" className="flex w-full items-center gap-2">
                      <BookOpen className="size-4" />
                      Docs
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem>
                    <Link href="/status" className="flex w-full items-center gap-2">
                      <MoonStar className="size-4" />
                      Status
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive" onClick={() => void onSignOut()}>
                    <LogOut className="size-4" />
                    Sign out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </header>

        <main id="main-content" className="min-w-0 flex-1 py-6">
          <div className="mx-auto w-full max-w-[1280px] px-4 sm:px-6">{children}</div>
        </main>
      </div>
    </div>
  );
}
