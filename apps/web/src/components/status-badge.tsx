import { Badge } from "@/components/ui/badge";
import type { ScanStatus } from "@/lib/types";
import { SCAN_STATUS_LABELS } from "@/lib/presentation";
import { cn } from "@/lib/utils";

const STATUS_CLASSES: Record<ScanStatus, string> = {
  queued: "border-border text-muted-foreground",
  running: "border-brand/40 bg-brand/10 text-brand-text",
  completed: "border-brand/40 bg-brand/10 text-foreground",
  failed: "border-severity-critical/40 bg-severity-critical/10 text-severity-critical",
  incomplete: "border-severity-high/40 bg-severity-high/10 text-severity-high",
};

export function StatusBadge({
  status,
  className,
}: {
  status: ScanStatus;
  className?: string;
}) {
  return (
    <Badge
      variant="outline"
      className={cn("rounded-full px-2.5 py-1 text-xs font-medium", STATUS_CLASSES[status], className)}
    >
      {SCAN_STATUS_LABELS[status]}
    </Badge>
  );
}
