import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/shared/lib/utils";

/**
 * A native select wearing the same chrome as Input, so filter rows line up
 * with the search fields beside them. Native rather than a listbox widget:
 * these are short, static option lists, and the platform control already
 * handles keyboard, mobile and assistive tech correctly.
 *
 * `aria-label` or a associated <label> is required by the caller; a bare
 * filter select with no name is unusable with a screen reader.
 */
export function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <div className="relative">
      <select
        className={cn(
          "h-9 w-full appearance-none rounded-md border border-input bg-card px-3 pr-8 text-sm",
          "transition-colors outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2 text-muted-foreground"
      />
    </div>
  );
}
