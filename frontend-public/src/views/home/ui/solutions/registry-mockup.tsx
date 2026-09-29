"use client";

import {
  Braces,
  Check,
  CornerDownLeft,
  Database,
  Info,
  LoaderCircle,
  MessageSquareText,
  RotateCcw,
  Server,
  TriangleAlert,
  WandSparkles,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { BrandIcon } from "@/shared/ui/brand-icon";
import styles from "./solutions.module.css";
import { useSequence } from "./use-sequence";

/*
 * Every field shown is one the registry tools really return
 * (`backend/cli/aevrin_cli/registry_tools.py`): a search result carries
 * slug, name, type and categories and a note that listing is curation, and
 * `get_registry_item` carries `install_configs`, built by
 * `services/marketplace/catalog.py`'s `build_install_config` with the same
 * secret-variable warning text. No item carries a grade (ADR-049). The items
 * themselves are fictional; "acme" names stand in for real publishers.
 */

const PROMPT = "find an MCP server for Postgres docs";
const TYPED = PROMPT.length;

const SCHEDULE: readonly number[] = [
  ...Array.from({ length: TYPED }, (_, i) => 300 + i * 42),
  2000, // prompt sent, search_registry running
  2800, // results arrive
  3600, // first result highlighted
  4100, // get_registry_item running
  4800, // item attached as context
  5200, // install config shown
];

type Row = {
  name: string;
  type: string;
  category: string;
  slug: string;
  icon: LucideIcon;
};

const ROWS: Row[] = [
  { name: "Acme Postgres Docs", type: "MCP server", category: "Databases", slug: "acme-postgres-docs", icon: Database },
  { name: "Acme Schema Browser", type: "MCP server", category: "Databases", slug: "acme-schema-browser", icon: Server },
  { name: "Postgres Query Review", type: "Skill", category: "Developer Tools", slug: "acme-pg-query-review", icon: WandSparkles },
  { name: "Safe Migration Plan", type: "Prompt", category: "Backend", slug: "acme-safe-migration", icon: MessageSquareText },
];

const CONFIG_LINES: { indent: number; text: string }[] = [
  { indent: 0, text: '"acme-postgres-docs": {' },
  { indent: 1, text: '"command": "npx",' },
  { indent: 1, text: '"args": ["@acme/pg-docs-mcp@1.4.2"],' },
  { indent: 1, text: '"env": { "DATABASE_URL": "" }' },
  { indent: 0, text: "}" },
];

function ToolCall({
  name,
  args,
  running,
  done,
  doneLabel,
  on,
}: {
  name: string;
  args: string;
  running: boolean;
  done: boolean;
  doneLabel: string;
  on: boolean;
}) {
  return (
    <div className={cn(styles.step, "flex min-w-0 items-center gap-2 text-[12.5px]")} data-on={on}>
      <span
        className={cn("size-1.5 shrink-0 rounded-full", done ? "bg-[var(--sb-ok)]" : "bg-[var(--mk-muted)]")}
      />
      <span className={cn(styles.mono, "shrink-0 font-medium")} style={{ color: "var(--mk-fg)" }}>
        {name}
      </span>
      <span className={cn(styles.mono, styles.dim, "min-w-0 truncate")}>{args}</span>
      <span className="ml-auto flex shrink-0 items-center gap-1 pl-2 text-xs">
        {done ? (
          <>
            <Check className={cn(styles.ok, "size-3.5")} />
            <span style={{ color: "var(--mk-fg)" }}>{doneLabel}</span>
          </>
        ) : running ? (
          <>
            <LoaderCircle className={cn(styles.spin, styles.dim, "size-3.5")} />
            <span className={styles.dim}>Running</span>
          </>
        ) : null}
      </span>
    </div>
  );
}

export function RegistryMockup() {
  const { ref, step, final, inView, replay } = useSequence<HTMLElement>(SCHEDULE);
  const at = (k: number) => step >= TYPED + k;
  const typing = step < TYPED;
  const typed = PROMPT.slice(0, Math.min(step, TYPED));
  const selected = at(3);
  const attached = at(5);

  return (
    <figure ref={ref} className={cn(styles.tile, "@container")}>
      <div
        aria-hidden="true"
        className="relative p-3 @min-[460px]:h-[600px] @min-[460px]:p-0"
      >
        {/* The agent session. */}
        <div
          className={cn(
            styles.panel,
            "flex flex-col overflow-hidden @min-[460px]:absolute @min-[460px]:top-5 @min-[460px]:left-5 @min-[460px]:right-14",
          )}
        >
          <div className="flex h-10 shrink-0 items-center gap-2 border-b px-3.5" style={{ borderColor: "var(--mk-line)" }}>
            <BrandIcon name="claude" className="size-4" />
            <span className="text-[13px] font-medium" style={{ color: "var(--mk-fg)" }}>
              Claude Code
            </span>
            <span className={cn(styles.mono, styles.dim, "hidden text-xs @min-[380px]:inline")}>~/acme-api</span>
            <span className={cn(styles.chip, "ml-auto")}>
              <span className="size-1.5 rounded-full bg-[var(--sb-ok)]" />
              <span className={styles.mono}>aevrin</span>
              <span className={styles.dim}>MCP</span>
            </span>
          </div>

          <div className="flex min-h-0 flex-1 flex-col gap-3 px-3.5 py-3.5">
            <p className="flex gap-2 text-[13.5px] leading-5" style={{ color: "var(--mk-fg)" }}>
              <span className={cn(styles.mono, styles.dim)}>&gt;</span>
              <span>
                {typed}
                {typing ? <span className={styles.caret} data-live={inView} /> : null}
              </span>
            </p>

            <ToolCall
              name="search_registry"
              args='query: "postgres docs", type: "mcp_server"'
              running={at(1)}
              done={at(2)}
              doneLabel="4 items"
              on={at(1)}
            />

            <div className={cn(styles.inset, styles.step, "overflow-hidden")} data-on={at(2)}>
              <p
                className={cn(styles.dim, "flex items-center gap-1.5 border-b px-3 py-1.5 text-xs")}
                style={{ borderColor: "var(--mk-line)" }}
              >
                <Info className="size-3.5 shrink-0" />
                <span className="truncate">Listing is curation, not a security assessment.</span>
              </p>
              <ul>
                {ROWS.map((row, index) => {
                  const Icon = row.icon;
                  const active = selected && index === 0;
                  return (
                    <li
                      key={row.slug}
                      data-active={active}
                      className={cn(
                        styles.row,
                        styles.fade,
                        "flex items-center gap-2.5 px-3 py-[7px]",
                        index < ROWS.length - 1 && "border-b",
                        attached && index > 0 && "opacity-45",
                      )}
                      style={{ borderColor: "var(--mk-line)" }}
                    >
                      <span
                        className="flex size-7 shrink-0 items-center justify-center rounded-md border"
                        style={{ borderColor: "var(--mk-line)", background: "var(--mk-surface)", color: "var(--mk-fg)" }}
                      >
                        <Icon className="size-3.5" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[13px] leading-[18px] font-medium" style={{ color: "var(--mk-fg)" }}>
                          {row.name}
                        </span>
                        <span className={cn(styles.dim, "block truncate text-xs leading-[18px]")}>
                          <span className="hidden @min-[400px]:inline">{row.category} · </span>
                          <span className="@min-[400px]:hidden">{row.type} · </span>
                          <span className={styles.mono}>{row.slug}</span>
                        </span>
                      </span>
                      <span className="hidden shrink-0 @min-[400px]:block">
                        <span className={styles.chip}>{row.type}</span>
                      </span>
                      <span className="flex w-5 shrink-0 justify-end">
                        {active && !attached ? (
                          <span className={styles.kbd}>
                            <CornerDownLeft className="size-3" />
                          </span>
                        ) : active && attached ? (
                          <Check className={cn(styles.ok, "size-3.5")} />
                        ) : null}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>

            <ToolCall
              name="get_registry_item"
              args='slug: "acme-postgres-docs"'
              running={at(4)}
              done={attached}
              doneLabel="Attached"
              on={at(4)}
            />
          </div>

          <div className="shrink-0 border-t p-2.5" style={{ borderColor: "var(--mk-line)" }}>
            <div
              className="flex min-h-10 flex-wrap items-center gap-2 rounded-lg border px-2.5 py-1.5"
              style={{ borderColor: "var(--mk-line)" }}
            >
              <span className={cn(styles.chip, styles.pop, "h-6")} data-on={attached}>
                <Database className="size-3" />
                <span className={styles.mono}>acme-postgres-docs</span>
              </span>
              <span className={cn(styles.dim, "text-[13px]")}>
                Ask a follow-up
                {step >= final ? <span className={styles.caret} data-live={inView} /> : null}
              </span>
            </div>
          </div>
        </div>

        {/* The install config the item carries, floated over the session. */}
        <div
          className={cn(
            styles.panel,
            styles.stepSide,
            "relative z-10 -mt-5 ml-5 p-3 @min-[460px]:absolute @min-[460px]:right-4 @min-[460px]:bottom-4 @min-[460px]:m-0 @min-[460px]:w-[324px]",
          )}
          data-on={at(6)}
        >
          <div className="flex items-center gap-2">
            <Braces className="size-3.5" style={{ color: "var(--mk-fg)" }} />
            <span className="text-[13px] font-medium" style={{ color: "var(--mk-fg)" }}>
              Install config
            </span>
            <span className={cn(styles.chip, "ml-auto")}>
              <BrandIcon name="claude" className="size-3" />
              Claude Code
            </span>
          </div>
          <pre className={cn(styles.code, styles.mono, "mt-2.5 overflow-hidden px-2.5 py-2 text-xs leading-[18px]")}>
            {CONFIG_LINES.map((line) => (
              <span key={line.text} className="block break-all" style={{ paddingLeft: `${line.indent * 14}px`, color: "var(--mk-fg)" }}>
                {line.text}
              </span>
            ))}
          </pre>
          <p className="mt-2.5 flex gap-1.5 text-xs leading-[18px]" style={{ color: "var(--mk-fg)" }}>
            <TriangleAlert className={cn(styles.warn, "mt-px size-3.5 shrink-0")} />
            <span>DATABASE_URL is a secret. Set it in your own environment; never commit it.</span>
          </p>
          <div className="mt-2.5 border-t pt-2.5" style={{ borderColor: "var(--mk-line)" }}>
            <p className={cn(styles.dim, "text-xs")}>Scan it before you install it</p>
            <p className={cn(styles.mono, "mt-1 text-xs leading-[18px] break-all")} style={{ color: "var(--mk-fg)" }}>
              aevrin scan mcp &quot;npx -y @acme/pg-docs-mcp@1.4.2&quot;
            </p>
          </div>
        </div>
      </div>

      <figcaption className="sr-only">
        Illustration: in Claude Code, a request for an MCP server for Postgres docs runs the
        registry tool search_registry, which returns four listings with their type, category and
        slug and a note that listing is curation, not a security assessment. The agent then reads
        one with get_registry_item, attaches it to the conversation, and shows its Claude Code
        install config with a warning that DATABASE_URL is a secret, and the command to scan it
        first. The listings are fictional.
      </figcaption>

      <div className="flex justify-end px-3 pb-3 @min-[460px]:absolute @min-[460px]:top-5 @min-[460px]:right-2.5 @min-[460px]:p-0">
        <button
          type="button"
          onClick={replay}
          aria-label="Replay the registry demo"
          className={cn(
            styles.focusRing,
            "flex size-8 items-center justify-center rounded-md border transition-colors hover:bg-[var(--mk-hover)]",
          )}
          style={{ borderColor: "var(--mk-line)", background: "var(--mk-surface)", color: "var(--mk-fg)" }}
        >
          <RotateCcw className="size-3.5" aria-hidden="true" />
        </button>
      </div>
    </figure>
  );
}
