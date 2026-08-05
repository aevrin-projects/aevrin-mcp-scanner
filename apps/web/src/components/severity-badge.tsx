import { Badge } from "@/components/ui/badge";
import type { Severity } from "@/lib/types";
import { cn } from "@/lib/utils";

const SEVERITY_CLASSES: Record<Severity, string> = {
  critical: "bg-severity-critical-solid text-severity-critical-foreground border-transparent",
  high: "bg-severity-high text-severity-high-foreground border-transparent",
  medium: "bg-severity-medium text-severity-medium-foreground border-transparent",
  low: "bg-severity-low text-severity-low-foreground border-transparent",
  info: "bg-muted text-muted-foreground border-transparent",
};

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <Badge className={cn(SEVERITY_CLASSES[severity], "uppercase tracking-wide", className)}>
      {severity}
    </Badge>
  );
}
