import * as React from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@/shared/lib/utils";

/**
 * "Technical details": the exact scanner data under a plain-language
 * explanation. Simple first, technical second, and never simple *instead*:
 * everything a security reviewer needs stays one click away.
 *
 * A native <details>, so it opens with Enter or Space and its state is
 * announced by screen readers with no script. Closed by default; a reader
 * who never opens it has still been told what matters.
 */
export function TechnicalDetails({
  label = "Technical details",
  className,
  children,
}: {
  label?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <details className={cn("group text-xs", className)}>
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-sm font-medium text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" aria-hidden="true" />
        {label}
      </summary>
      <div className="mt-2 space-y-1.5 text-muted-foreground">{children}</div>
    </details>
  );
}
