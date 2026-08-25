import { Badge } from "@/shared/ui/badge";
import { cn } from "@/shared/lib/utils";
import { SCOPE_DESCRIPTIONS, SCOPE_LABELS } from "../model/labels";
import type { ConfigScope } from "../model/types";

const SCOPE_CLASSES: Record<ConfigScope, string> = {
  managed: "border-brand/40 bg-brand/10 text-brand-text",
  user: "border-border text-foreground",
  project: "border-border text-foreground",
  local: "border-border text-muted-foreground",
};

export function ScopeBadge({ scope, className }: { scope: ConfigScope; className?: string }) {
  return (
    <Badge
      variant="outline"
      title={SCOPE_DESCRIPTIONS[scope]}
      className={cn("rounded-full px-2 py-0.5 text-xs font-medium", SCOPE_CLASSES[scope], className)}
    >
      {SCOPE_LABELS[scope]}
    </Badge>
  );
}
