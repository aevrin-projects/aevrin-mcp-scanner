import { Badge } from "@/shared/ui/badge";
import { cn } from "@/shared/lib/utils";
import type { PolicyOutcome } from "../model/types";

const DECISION_LABELS = {
  allowed: "Allowed",
  approval_required: "Approval required",
  blocked: "Blocked by policy",
} as const;

const DECISION_CLASSES = {
  allowed: "border-border text-muted-foreground",
  approval_required: "border-severity-medium/40 bg-severity-medium/10 text-severity-medium",
  blocked: "border-severity-critical/40 bg-severity-critical/10 text-severity-critical",
} as const;

/** Nothing is rendered when no policy is switched on. Showing "Allowed" for
 *  an account with no policies would imply a review that never happened. */
export function PolicyBadge({ policy, className }: { policy: PolicyOutcome | null; className?: string }) {
  if (!policy) return null;
  return (
    <Badge
      variant="outline"
      title={policy.reasons.join("; ") || undefined}
      className={cn(
        "rounded-full px-2 py-0.5 text-xs font-medium",
        DECISION_CLASSES[policy.decision],
        className,
      )}
    >
      {DECISION_LABELS[policy.decision]}
    </Badge>
  );
}
