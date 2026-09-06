"use client";

import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AdminHeader } from "./admin-header";
import { AppSidebar } from "./app-sidebar";

/**
 * The admin application shell: collapsible sidebar, sticky header, content.
 *
 * Replaces a single horizontal bar of links. The panel had four pages, one of
 * which the bar did not list, and no indication of which one you were on -
 * neither scales, and both are the kind of thing that stops being noticed by
 * whoever built it.
 *
 * `TooltipProvider` is mounted here rather than in the root layout because
 * the collapsed sidebar is the only part of the product using tooltips; the
 * rest of the app should not pay for a provider it never reads.
 */
export function AdminShell({ children }: { children: React.ReactNode }) {
  return (
    <TooltipProvider delay={0}>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="min-w-0">
          <AdminHeader />
          {/* A div, not a <main>. `SidebarInset` already renders the page's
              <main> landmark, and nesting a second one gave every admin page
              two - which is invalid, and leaves a screen reader's "jump to
              main content" ambiguous. The id stays so a skip link still has a
              target. Found by an axe run, not by reading the component. */}
          <div id="admin-content" className="flex flex-1 flex-col gap-4 p-4 sm:gap-6 sm:p-6">
            {children}
          </div>
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  );
}
