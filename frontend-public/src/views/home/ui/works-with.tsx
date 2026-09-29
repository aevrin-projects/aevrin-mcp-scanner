import { Server } from "lucide-react";
import { BrandIcon, type BrandName } from "@/shared/ui/brand-icon";

/**
 * In place of Folio's customer-logo marquee: the tools Aevrin actually reads
 * or scans, each with what it does with them. No customer logos, because
 * there are none to show. Marks are monochrome so the strip stays neutral.
 */
const ITEMS: { name: string; detail: string; brand?: BrandName }[] = [
  { name: "Claude Code", detail: "Install hook and agent posture", brand: "claude" },
  { name: "Codex", detail: "Agent posture", brand: "openai" },
  { name: "GitHub", detail: "Repositories as scan targets", brand: "github" },
  { name: "MCP servers", detail: "By URL or by start command" },
];

export function WorksWith() {
  return (
    <section aria-labelledby="works-with-title" className="mk-container pb-4 md:pb-8">
      <h2 id="works-with-title" className="mk-eyebrow text-center">
        Works with what you already run
      </h2>
      <ul className="mt-6 grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-[var(--mk-line)] bg-[var(--mk-line)] min-[480px]:grid-cols-2 lg:grid-cols-4">
        {ITEMS.map((item) => (
          <li key={item.name} className="flex items-center gap-3.5 bg-[var(--mk-bg)] px-5 py-4">
            <span className="grid size-9 shrink-0 place-items-center rounded-lg border border-[var(--mk-line)] text-[var(--mk-fg)]">
              {item.brand ? (
                <BrandIcon name={item.brand} mono className="size-4" />
              ) : (
                <Server className="size-4" aria-hidden="true" />
              )}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-medium text-[var(--mk-fg-strong)]">{item.name}</span>
              <span className="block text-[13px] text-[var(--mk-muted)]">{item.detail}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
