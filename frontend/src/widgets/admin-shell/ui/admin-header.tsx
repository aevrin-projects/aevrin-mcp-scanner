"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/features/theme";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/shared/ui/separator";

/** Path segment -> the label the nav uses for it, so a breadcrumb and a
 *  sidebar entry never disagree about what a page is called. Segments absent
 *  here are IDs, which are shown truncated rather than guessed at: looking up
 *  an account's email to title its own page would be a second fetch of data
 *  the page below is already loading. */
const SEGMENT_LABELS: Record<string, string> = {
  admin: "Admin",
  analytics: "Analytics",
  audit: "Audit log",
  marketplace: "Marketplace",
  users: "Accounts",
};

function labelFor(segment: string): string {
  const known = SEGMENT_LABELS[segment];
  if (known) return known;
  // An opaque id. Shortened so a UUID cannot push the header into a second
  // line on a narrow viewport.
  return segment.length > 12 ? `${segment.slice(0, 8)}…` : segment;
}

export function AdminHeader() {
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);

  const crumbs = segments.map((segment, index) => ({
    segment,
    label: labelFor(segment),
    href: `/${segments.slice(0, index + 1).join("/")}`,
    isLast: index === segments.length - 1,
  }));

  return (
    <header className="sticky top-0 z-40 flex h-16 shrink-0 items-center gap-2 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="flex w-full items-center gap-2 px-4">
        <SidebarTrigger className="-ms-1" />
        <Separator orientation="vertical" className="me-2 h-4" />
        <Breadcrumb>
          <BreadcrumbList>
            {crumbs.map((crumb) => (
              <BreadcrumbItem key={crumb.href}>
                {crumb.isLast ? (
                  <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                ) : (
                  <>
                    <BreadcrumbLink render={<Link href={crumb.href} />}>{crumb.label}</BreadcrumbLink>
                    <BreadcrumbSeparator />
                  </>
                )}
              </BreadcrumbItem>
            ))}
          </BreadcrumbList>
        </Breadcrumb>
        <div className="ms-auto flex items-center gap-2">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
