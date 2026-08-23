import * as React from "react";
import { cn } from "@/shared/lib/utils";

/**
 * Tabler's page header: a small uppercase pretitle naming the area, the page
 * title under it, and the page's actions pinned right on one baseline.
 *
 * The pretitle is what makes a multi-screen product feel located rather than
 * just titled, so it is the default rather than an extra.
 */
export function PageHeader({
  pretitle,
  title,
  description,
  actions,
  className,
}: {
  pretitle?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-3 sm:flex-row sm:items-center", className)}>
      <div className="min-w-0 flex-1">
        {pretitle ? <div className="subheader">{pretitle}</div> : null}
        <h1 className="truncate text-xl leading-7 font-semibold tracking-tight">{title}</h1>
        {description ? (
          <p className="mt-1.5 max-w-3xl text-[13px] leading-5 text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
