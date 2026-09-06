"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronsUpDown, LayoutDashboard, LogOut } from "lucide-react";
import { useAdminSession } from "@/features/admin-gate";
import { createClient } from "@/shared/lib/supabase/client";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/ui/dropdown-menu";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from "@/components/ui/sidebar";

/** Two letters from the email, which is the only identity an admin session
 *  carries - there is no display name and no avatar to fetch. Rendered as a
 *  tile rather than an <Avatar> for exactly that reason: an avatar component
 *  whose image never loads is a fallback with extra steps. */
function initials(email: string | null): string {
  if (!email) return "??";
  const [local] = email.split("@");
  const parts = local.split(/[._-]+/).filter(Boolean);
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : local.slice(0, 2)).toUpperCase();
}

export function NavUser() {
  const { email } = useAdminSession();
  const { isMobile } = useSidebar();
  const router = useRouter();

  // The same sign-out the product shell uses, not a second one: an admin who
  // signs out here must lose the Supabase session, not just the admin panel.
  async function signOut() {
    await createClient().auth.signOut();
    router.replace("/login");
    router.refresh();
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={<SidebarMenuButton size="lg" aria-label="Open admin account menu" />}
          >
            <span className="flex aspect-square size-8 items-center justify-center rounded-md bg-muted text-[11px] font-semibold ring-1 ring-border ring-inset">
              {initials(email)}
            </span>
            <span className="grid flex-1 text-left text-sm leading-tight">
              <span className="truncate font-medium">Administrator</span>
              <span className="truncate text-xs text-muted-foreground">{email ?? "Unknown account"}</span>
            </span>
            <ChevronsUpDown className="ms-auto size-4 text-muted-foreground" />
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="min-w-56"
            side={isMobile ? "bottom" : "right"}
            align="end"
            sideOffset={4}
          >
            <div className="px-2 py-1.5">
              <p className="subheader">Signed in as</p>
              <p className="mt-1 truncate text-sm">{email ?? "Unknown account"}</p>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem>
              <Link href="/dashboard" className="flex w-full items-center gap-2">
                <LayoutDashboard className="size-4" />
                Back to product
              </Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onClick={() => void signOut()}>
              <LogOut className="size-4" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
