import * as React from "react";
import { cn } from "@/shared/lib/utils";

/**
 * The surface every product screen is built from, following Tabler's card
 * anatomy: a hairline-bordered white panel on a slightly recessed page, with
 * a 20px horizontal rhythm shared by the header, the body and the table cells
 * inside it. Keeping that one number consistent is most of what makes a dense
 * dashboard read as deliberate rather than assembled.
 *
 * Colours and type come from the existing tokens; only the structure is
 * borrowed.
 */
export function Panel({
  className,
  children,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "flex flex-col rounded-lg border border-border bg-card text-card-foreground",
        "shadow-[0_1px_2px_0_oklch(0_0_0/0.03)]",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function PanelHeader({ className, children, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "flex min-h-[3.5rem] items-center gap-3 border-b border-border px-5 py-4",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function PanelTitle({ className, children, ...props }: React.ComponentProps<"h3">) {
  return (
    <h3 className={cn("text-base leading-6 font-medium", className)} {...props}>
      {children}
    </h3>
  );
}

export function PanelSubtitle({ className, children, ...props }: React.ComponentProps<"p">) {
  return (
    <p className={cn("mt-0.5 text-[13px] leading-5 text-muted-foreground", className)} {...props}>
      {children}
    </p>
  );
}

/** Right-aligned controls in a panel header. `ms-auto` is what pins them. */
export function PanelActions({ className, children, ...props }: React.ComponentProps<"div">) {
  return (
    <div className={cn("ms-auto flex shrink-0 items-center gap-2", className)} {...props}>
      {children}
    </div>
  );
}

export function PanelBody({ className, children, ...props }: React.ComponentProps<"div">) {
  return (
    <div className={cn("flex-1 px-5 py-4", className)} {...props}>
      {children}
    </div>
  );
}

/** A panel whose only content is a full-bleed table: drops the body padding
 *  so the table's own 20px cell inset lines up with the header above it. */
export function PanelTableWrap({ className, children, ...props }: React.ComponentProps<"div">) {
  return (
    <div className={cn("w-full overflow-x-auto", className)} tabIndex={0} {...props}>
      {children}
    </div>
  );
}
