"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowUpRight, BarChart3, ScrollText, ShieldCheck, Store, Users } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import { NavUser } from "./nav-user";

/**
 * Admin navigation.
 *
 * Every entry here resolves to a route that exists. That is worth stating
 * because the previous header nav listed three of the four admin pages and
 * omitted `/admin/marketplace` entirely - it was reachable only by typing the
 * URL, which is indistinguishable from the page not existing.
 *
 * Grouped by what an admin is doing rather than by which service backs it:
 * looking at the business, acting on an account or a listing, or reviewing
 * what was done.
 */
const NAV_GROUPS = [
  {
    label: "Overview",
    items: [{ href: "/admin/analytics", label: "Analytics", icon: BarChart3 }],
  },
  {
    label: "Manage",
    items: [
      { href: "/admin", label: "Accounts", icon: Users },
      { href: "/admin/marketplace", label: "Marketplace", icon: Store },
    ],
  },
  {
    label: "Security",
    items: [{ href: "/admin/audit", label: "Audit log", icon: ScrollText }],
  },
] as const;

/** `/admin` is a prefix of every other admin route, so it only matches exactly.
 *  Everything else matches its own subtree, which is what keeps "Accounts"
 *  from lighting up while you are three levels deep in Marketplace. */
function isActive(pathname: string, href: string): boolean {
  return href === "/admin" ? pathname === "/admin" : pathname.startsWith(href);
}

export function AppSidebar() {
  const pathname = usePathname();
  const { setOpenMobile } = useSidebar();

  return (
    <Sidebar collapsible="icon" variant="inset">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="lg"
              render={<Link href="/admin" onClick={() => setOpenMobile(false)} />}
            >
              <span className="flex aspect-square size-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <ShieldCheck className="size-4" />
              </span>
              <span className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">Aevrin</span>
                <span className="truncate text-xs text-muted-foreground">Administration</span>
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {NAV_GROUPS.map((group) => (
          <SidebarGroup key={group.label}>
            <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
            <SidebarMenu>
              {group.items.map((item) => {
                const active = isActive(pathname, item.href);
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      isActive={active}
                      tooltip={item.label}
                      render={
                        <Link
                          href={item.href}
                          onClick={() => setOpenMobile(false)}
                          // The active state is signalled by a background
                          // colour, which is not a signal at all to a screen
                          // reader. This is what it announces instead.
                          aria-current={active ? "page" : undefined}
                        />
                      }
                    >
                      <item.icon />
                      <span>{item.label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroup>
        ))}

        <SidebarGroup className="mt-auto">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton tooltip="Back to product" render={<Link href="/dashboard" />}>
                <ArrowUpRight />
                <span>Back to product</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
