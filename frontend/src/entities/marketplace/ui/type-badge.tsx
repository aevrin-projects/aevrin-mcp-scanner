import {
  AppWindow,
  Blocks,
  Bot,
  BookOpen,
  Boxes,
  Cloud,
  Database,
  FileCode2,
  FolderGit2,
  LayoutTemplate,
  Library,
  MessageSquareText,
  Package,
  Plug,
  Server,
  Sparkles,
  SquareTerminal,
  Workflow,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/shared/ui/badge";
import { cn } from "@/shared/lib/utils";
import { ITEM_TYPE_LABELS, type ItemType } from "../model/types";

/**
 * What a registry item is, as an icon and a word.
 *
 * Always both: the icon alone is a guess for anyone who does not know the
 * set, and to a screen reader it is nothing. The word carries the meaning.
 */

export const ITEM_TYPE_ICONS: Record<ItemType, LucideIcon> = {
  mcp_server: Server,
  skill: Sparkles,
  prompt: MessageSquareText,
  tool: Wrench,
  agent: Bot,
  component: Blocks,
  template: LayoutTemplate,
  workflow: Workflow,
  library: Library,
  cli: SquareTerminal,
  backend: Database,
  frontend: AppWindow,
  infrastructure: Cloud,
  product: Package,
  repository: FolderGit2,
  integration: Plug,
  dataset: Boxes,
  documentation: BookOpen,
  other: FileCode2,
};

export function TypeBadge({ type, className }: { type: ItemType; className?: string }) {
  const Icon = ITEM_TYPE_ICONS[type];
  return (
    <Badge variant="outline" className={cn("gap-1 text-[11px]", className)}>
      <Icon className="size-3" aria-hidden="true" />
      {ITEM_TYPE_LABELS[type].one}
    </Badge>
  );
}
