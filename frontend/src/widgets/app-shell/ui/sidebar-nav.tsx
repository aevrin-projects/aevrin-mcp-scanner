"use client";

import Link from "next/link";
import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { NAV_GROUPS, isActivePath, type NavGroup } from "./nav-items";

function NavLinks({
  group,
  pathname,
  onNavigate,
}: {
  group: NavGroup;
  pathname: string;
  onNavigate?: () => void;
}) {
  return (
    <ul className="flex flex-col gap-0.5">
      {group.items.map((item) => {
        const active = isActivePath(pathname, item);
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-sm transition-colors",
                active
                  ? "bg-muted font-medium text-foreground"
                  : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
              )}
            >
              <item.icon className="size-4 shrink-0" aria-hidden="true" />
              {item.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function CollapsibleGroup({
  group,
  pathname,
  onNavigate,
}: {
  group: NavGroup;
  pathname: string;
  onNavigate?: () => void;
}) {
  // Open by default. A collapsed group hides the thing someone came for, and
  // the group holding the current page starts open regardless of what they
  // last collapsed, so navigation never leaves the active item invisible.
  const holdsActivePage = group.items.some((item) => isActivePath(pathname, item));
  const [open, setOpen] = useState(true);
  const expanded = open || holdsActivePage;
  const id = `nav-group-${group.label?.replace(/\s+/g, "-").toLowerCase()}`;

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={expanded}
        aria-controls={id}
        className="flex w-full items-center gap-1 px-2.5 py-1.5 text-[11px] font-semibold tracking-[0.08em] text-muted-foreground uppercase transition-colors hover:text-foreground"
      >
        {group.label}
        <ChevronDown
          className={cn("size-3.5 transition-transform", expanded ? "" : "-rotate-90")}
          aria-hidden="true"
        />
      </button>
      <div id={id} hidden={!expanded}>
        <NavLinks group={group} pathname={pathname} onNavigate={onNavigate} />
      </div>
    </div>
  );
}

export function SidebarNav({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <nav aria-label="Product" className="flex flex-col gap-4">
      {NAV_GROUPS.map((group) =>
        group.label === null ? (
          <NavLinks key="root" group={group} pathname={pathname} onNavigate={onNavigate} />
        ) : (
          <CollapsibleGroup
            key={group.label}
            group={group}
            pathname={pathname}
            onNavigate={onNavigate}
          />
        ),
      )}
    </nav>
  );
}
