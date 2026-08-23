"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BookOpen,
  ChartNoAxesCombined,
  ChevronDown,
  CreditCard,
  History,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  MoonStar,
  ScanSearch,
  TerminalSquare,
} from "lucide-react";
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
import { cn } from "@/shared/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/scans/new", label: "New scan", icon: ScanSearch },
  { href: "/scans/history", label: "Scan history", icon: History },
  { href: "/usage", label: "Usage", icon: ChartNoAxesCombined },
  { href: "/integrations", label: "Integrations", icon: TerminalSquare },
  { href: "/settings/api-keys", label: "API keys", icon: KeyRound },
  { href: "/settings/billing", label: "Billing", icon: CreditCard },
];

/** Tabler's container: one max width and one gutter, shared by the navbar,
 *  the nav row and the page body, so every edge on the screen lines up. */
const CONTAINER = "mx-auto w-full max-w-[1320px] px-4 sm:px-6";

function isActivePath(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function accountMonogram(email: string) {
  const seed = email.split("@")[0]?.replace(/[^a-zA-Z0-9]/g, "") ?? "";
  return seed.slice(0, 2).toUpperCase() || "AV";
}

/**
 * Tabler's horizontal `navbar-nav`: the active item is marked by a 2px rule
 * under it rather than a filled pill, which is what keeps a seven-item row
 * from reading as seven buttons. `aria-current` carries the same fact for
 * anyone who cannot see the rule.
 */
function DesktopNav({ pathname }: { pathname: string }) {
  return (
    <nav aria-label="Product" className="hidden md:block">
      <ul className="-mb-px flex items-center gap-1">
        {NAV_ITEMS.map((item) => {
          const active = isActivePath(pathname, item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2 border-b-2 px-3 py-3 text-sm whitespace-nowrap transition-colors",
                  active
                    ? "border-brand font-medium text-foreground"
                    : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
                )}
              >
                <item.icon className="size-4 shrink-0" aria-hidden="true" />
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function MobileNav({ pathname, onNavigate }: { pathname: string; onNavigate: () => void }) {
  return (
    <nav aria-label="Product" className="flex flex-col gap-0.5">
      {NAV_ITEMS.map((item) => {
        const active = isActivePath(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-3 py-2.5 text-sm transition-colors",
              active
                ? "bg-muted font-medium text-foreground"
                : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
            )}
          >
            <item.icon className="size-4 shrink-0" aria-hidden="true" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

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
    <div className="flex min-h-screen flex-col bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-sm"
      >
        Skip to content
      </a>

      {/* Row one: identity and account controls. Tabler splits the brand row
          from the nav row so the product's name and the person's account
          never compete with navigation for the same horizontal space. */}
      <header className="border-b border-border bg-card">
        <div className={cn(CONTAINER, "flex h-16 items-center gap-3")}>
          <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
            <DialogTrigger
              render={
                <Button variant="outline" size="icon-sm" aria-label="Open navigation" className="md:hidden" />
              }
            >
              <Menu className="size-4" />
            </DialogTrigger>
            <DialogContent className="top-0 left-0 flex h-full max-w-[320px] translate-x-0 translate-y-0 flex-col items-stretch gap-0 rounded-none border-r border-border p-0">
              <DialogHeader className="shrink-0 border-b border-border px-5 py-4">
                <DialogTitle className="flex items-center gap-3">
                  <Image src="/logo.png" alt="" width={22} height={24} />
                  Aevrin
                </DialogTitle>
              </DialogHeader>
              <div className="min-h-0 flex-1 overflow-y-auto p-3">
                <MobileNav pathname={pathname} onNavigate={() => setMobileOpen(false)} />
              </div>
            </DialogContent>
          </Dialog>

          <Link href="/dashboard" className="flex shrink-0 items-center gap-2 font-semibold">
            <Image src="/logo.png" alt="" width={20} height={22} priority />
            <span className="tracking-[0.12em] uppercase">Aevrin</span>
          </Link>

          {tier ? (
            <Link
              href="/settings/billing"
              className="hidden shrink-0 rounded-full border border-border px-2 py-0.5 text-[11px] font-medium text-muted-foreground capitalize transition-colors hover:text-foreground sm:inline-block"
            >
              {tier}
            </Link>
          ) : null}

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
                  <Link href="/docs" className="flex w-full items-center gap-2">
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

      {/* Row two: navigation. Sticky on its own so the tabs stay reachable
          while a long findings table scrolls, without dragging the whole
          128px of chrome down the page with them. */}
      <div className="sticky top-0 z-30 hidden border-b border-border bg-card/95 backdrop-blur md:block">
        <div className={CONTAINER}>
          <DesktopNav pathname={pathname} />
        </div>
      </div>

      <main id="main-content" className="min-w-0 flex-1 py-6">
        <div className={CONTAINER}>{children}</div>
      </main>
    </div>
  );
}
