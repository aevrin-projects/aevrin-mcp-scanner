import * as React from "react";
import { cn } from "@/shared/lib/utils";

/**
 * Tabler's `table table-vcenter card-table`, rebuilt on the project's tokens.
 *
 * The parts worth copying: column headers as tiny uppercase muted labels on a
 * recessed band, 20px outer cell inset so the first column lines up with the
 * panel header above, a hairline under every row, and a hover tint that makes
 * a long list scannable by row rather than by column.
 */
export function Table({ className, children, ...props }: React.ComponentProps<"table">) {
  return (
    <table className={cn("w-full border-collapse text-left text-sm", className)} {...props}>
      {children}
    </table>
  );
}

export function THead({ className, children, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead className={cn("border-b border-border bg-muted/60", className)} {...props}>
      {children}
    </thead>
  );
}

export function TH({ className, children, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      scope="col"
      className={cn(
        "px-3 py-2 text-xs leading-4 font-medium tracking-[0.04em] text-muted-foreground uppercase",
        "first:pl-5 last:pr-5",
        className,
      )}
      {...props}
    >
      {children}
    </th>
  );
}

export function TBody({ className, children, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody className={cn(className)} {...props}>
      {children}
    </tbody>
  );
}

export function TR({ className, children, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      className={cn("border-b border-border transition-colors last:border-0 hover:bg-muted/50", className)}
      {...props}
    >
      {children}
    </tr>
  );
}

export function TD({ className, children, ...props }: React.ComponentProps<"td">) {
  return (
    <td className={cn("px-3 py-3 align-middle first:pl-5 last:pr-5", className)} {...props}>
      {children}
    </td>
  );
}
