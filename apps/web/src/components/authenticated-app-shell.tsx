"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  BookOpen,
  ChevronDown,
  CreditCard,
  KeyRound,
  LayoutDashboard,
  Menu,
  ChartNoAxesCombined,
  ScanSearch,
  TerminalSquare,
  History,
  LogOut,
  MoonStar,
} from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/scans/new", label: "New scan", icon: ScanSearch },
  { href: "/scans/history", label: "Scan history", icon: History },
  { href: "/usage", label: "Usage", icon: ChartNoAxesCombined },
  { href: "/integrations", label: "Integrations", icon: TerminalSquare },
  { href: "/settings/api-keys", label: "API keys", icon: KeyRound },
  { href: "/settings/billing", label: "Billing", icon: CreditCard },
];

function isActivePath(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function accountMonogram(email: string) {
  const seed = email.split("@")[0]?.replace(/[^a-zA-Z0-9]/g, "") ?? "";
  return seed.slice(0, 2).toUpperCase() || "AV";
}

function NavLinks({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-1">
      {NAV_ITEMS.map((item) => {
        const active = isActivePath(pathname, item.href);

        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors",
              active
                ? "bg-brand/12 text-foreground ring-1 ring-brand/20"
                : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
            )}
          >
            <item.icon className={cn("size-4", active ? "text-brand-text" : "")} />
            <span>{item.label}</span>
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
  const monogram = accountMonogram(email);

  return (
    <div className="min-h-screen bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:text-foreground"
      >
        Skip to content
      </a>

      <div className="flex min-h-screen w-full">
        <aside className="hidden w-[260px] shrink-0 border-r border-border/80 bg-card/35 px-4 py-6 xl:w-[280px] lg:flex lg:flex-col lg:gap-8">
          <div className="flex items-center gap-3 px-3">
            <Image src="/logo.png" alt="" width={24} height={26} priority />
            <div>
              <div className="text-lg font-semibold tracking-[0.12em] text-foreground uppercase">Aevrin</div>
              <div className="text-xs text-muted-foreground">MCP Security Scanner</div>
            </div>
          </div>

          <div className="space-y-6">
            <div className="space-y-2">
              <p className="px-3 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                Workspace
              </p>
              <NavLinks pathname={pathname} />
            </div>

            <div className="rounded-2xl border border-border/80 bg-background/70 p-4">
              <p className="text-sm font-medium text-foreground">Security workflow</p>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Start a scan, review incomplete coverage honestly, and verify fixes with a repeat scan.
              </p>
              <Link
                href="/integrations"
                className="mt-4 inline-flex items-center gap-2 text-sm text-brand-text hover:text-foreground"
              >
                <BookOpen className="size-4" />
                CLI and hook setup
              </Link>
            </div>
          </div>
        </aside>

        <div className="flex min-h-screen min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-border/80 bg-background/90 backdrop-blur">
            <div className="flex h-16 items-center justify-between px-4 sm:px-6 lg:px-10">
              <div className="flex items-center gap-3 lg:hidden">
                <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
                  <DialogTrigger render={<Button variant="outline" size="icon-sm" aria-label="Open navigation" />}>
                    <Menu className="size-4" />
                  </DialogTrigger>
                  <DialogContent className="left-0 top-0 h-full max-w-[320px] translate-x-0 translate-y-0 rounded-none border-r border-border p-0">
                    <DialogHeader className="border-b border-border px-5 py-4">
                      <DialogTitle className="flex items-center gap-3">
                        <Image src="/logo.png" alt="" width={22} height={24} />
                        Aevrin
                      </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-6 px-4 py-5">
                      <NavLinks pathname={pathname} onNavigate={() => setMobileOpen(false)} />
                    </div>
                  </DialogContent>
                </Dialog>
                <Link href="/dashboard" className="flex items-center gap-2 font-semibold">
                  <Image src="/logo.png" alt="" width={20} height={22} />
                  <span className="tracking-[0.12em] uppercase">Aevrin</span>
                </Link>
              </div>

              <div className="hidden lg:block">
                <p className="text-sm font-medium text-foreground">Authenticated product workspace</p>
                <p className="text-xs text-muted-foreground">
                  Use real scan evidence, coverage, and remediation data only.
                </p>
              </div>

              <div className="flex items-center gap-2 sm:gap-3">
                <Button render={<Link href="/scans/new" />} className="hidden sm:inline-flex">
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
                    <span className="flex size-8 items-center justify-center rounded-full bg-brand/14 text-xs font-semibold tracking-[0.12em] text-foreground ring-1 ring-border">
                      {monogram}
                    </span>
                    <ChevronDown className="size-4 text-muted-foreground" />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-64">
                    <DropdownMenuGroup>
                      <div className="px-2 py-1.5">
                        <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
                          Account
                        </p>
                        <p className="mt-1 text-sm text-foreground">{email}</p>
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

          <main
            id="main-content"
            className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-7 xl:px-9 lg:py-8"
          >
            <div className="flex w-full flex-col gap-6">{children}</div>
          </main>
        </div>
      </div>
    </div>
  );
}
