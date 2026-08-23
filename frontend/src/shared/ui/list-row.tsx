import * as React from "react";
import Link from "next/link";
import { cn } from "@/shared/lib/utils";

/**
 * Tabler's `list-group-flush list-group-hoverable`: rows separated by a
 * hairline with no outer border of their own, so the panel supplies the
 * frame. Used wherever a table would be one column too few to earn headers.
 */
export function ListGroup({ className, children, ...props }: React.ComponentProps<"ul">) {
  return (
    <ul className={cn("divide-y divide-border", className)} {...props}>
      {children}
    </ul>
  );
}

export function ListRow({
  href,
  leading,
  title,
  subtitle,
  trailing,
  className,
}: {
  href?: string;
  leading?: React.ReactNode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  trailing?: React.ReactNode;
  className?: string;
}) {
  const body = (
    <>
      {leading ? <div className="shrink-0">{leading}</div> : null}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{title}</div>
        {subtitle ? (
          <div className="truncate text-[13px] leading-5 text-muted-foreground">{subtitle}</div>
        ) : null}
      </div>
      {trailing ? <div className="shrink-0">{trailing}</div> : null}
    </>
  );

  const shell = cn("flex items-center gap-3 px-5 py-3.5", className);

  return (
    <li>
      {href ? (
        <Link
          href={href}
          className={cn(
            shell,
            "transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
          )}
        >
          {body}
        </Link>
      ) : (
        <div className={shell}>{body}</div>
      )}
    </li>
  );
}
