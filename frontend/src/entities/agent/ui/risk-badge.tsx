import { Badge } from "@/shared/ui/badge";
import { cn } from "@/shared/lib/utils";
import { RISK_LABELS } from "../model/labels";
import type { PostureRisk } from "../model/types";

/** Letter and word, never colour alone: the same rule the severity badges
 *  elsewhere follow, for the same reason. */
const RISK_CLASSES: Record<PostureRisk, string> = {
  low: "border-border text-muted-foreground",
  medium: "border-severity-medium/40 bg-severity-medium/10 text-severity-medium",
  high: "border-severity-high/40 bg-severity-high/10 text-severity-high",
  critical: "border-severity-critical/40 bg-severity-critical/10 text-severity-critical",
};

export function RiskBadge({ risk, className }: { risk: PostureRisk; className?: string }) {
  return (
    <Badge
      variant="outline"
      className={cn("rounded-full px-2.5 py-1 text-xs font-medium", RISK_CLASSES[risk], className)}
    >
      {RISK_LABELS[risk]} risk
    </Badge>
  );
}
