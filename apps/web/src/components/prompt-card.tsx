"use client";

import { useState } from "react";
import { Bot, Check, ChevronDown, Copy, Webhook } from "lucide-react";
import { AGENT_HOOK_PROMPT, AGENT_INSTALL_PROMPT } from "@/lib/onboarding";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * The one prompt surface in the product. Previously three near-identical
 * `PromptPanel` copies existed (landing, /integrations, /settings/api-keys),
 * each dumping ~40 lines of monospace inline — which is both a wall of text
 * and three places to keep in sync.
 *
 * The only action anyone takes on a prompt is *copy*, so copy is the primary
 * button and everything else is secondary: a short summary of what the prompt
 * will do, and an icon-only disclosure for people who want to read it first.
 * The reveal animates via a `grid-rows` transition rather than `<details>`,
 * because a raw details element snaps open with no motion.
 */

export type PromptCardPreset = {
  title: string;
  description: string;
  steps: string[];
  value: string;
  copyLabel: string;
  Icon: typeof Bot;
};

export const INSTALL_PROMPT_CARD: PromptCardPreset = {
  title: "AI agent install prompt",
  description: "Paste into Claude Code or another agent to have it install and verify the CLI for you.",
  steps: [
    "Detects your OS and shell — no sudo, no system Python changes",
    "Picks npm or pipx, never both, and installs the CLI",
    "Pauses for you to approve device login in the browser",
    "Ends with a local scan you can run to confirm it works",
  ],
  value: AGENT_INSTALL_PROMPT,
  copyLabel: "Copy install prompt",
  Icon: Bot,
};

export const HOOK_PROMPT_CARD: PromptCardPreset = {
  title: "AI agent hook prompt",
  description: "Paste into Claude Code to have it wire the MCP pre-install hook into a project.",
  steps: [
    "Runs aevrin hook setup and waits for your device approval",
    "Merges the PreToolUse entries into .claude/settings.json",
    "Preserves every existing key and hook already in the file",
    "Validates the JSON and reports exactly what it covers",
  ],
  value: AGENT_HOOK_PROMPT,
  copyLabel: "Copy hook prompt",
  Icon: Webhook,
};

export function PromptCard({
  preset,
  className,
}: {
  preset: PromptCardPreset;
  className?: string;
}) {
  const { title, description, steps, value, copyLabel, Icon } = preset;
  const [copied, setCopied] = useState(false);
  const [open, setOpen] = useState(false);
  const lineCount = value.trim().split("\n").length;

  async function handleCopy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <section
      className={cn(
        "group/prompt relative overflow-hidden rounded-xl border border-border bg-card transition-colors hover:border-brand/30",
        className,
      )}
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-24 opacity-0 transition-opacity duration-500 group-hover/prompt:opacity-100"
        style={{
          background:
            "radial-gradient(90% 100% at 15% 0%, color-mix(in oklab, var(--brand) 12%, transparent), transparent 70%)",
        }}
      />

      <div className="relative p-5">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-brand/25 bg-brand/10">
            <Icon className="size-4 text-brand-text" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="text-[14px] font-medium text-foreground">{title}</h3>
            <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{description}</p>
          </div>
        </div>

        <ol className="mt-4 space-y-2">
          {steps.map((step, index) => (
            <li key={step} className="flex items-start gap-2.5">
              <span className="mt-px flex size-4.5 shrink-0 items-center justify-center rounded-full border border-border font-mono text-[10px] text-muted-foreground">
                {index + 1}
              </span>
              <span className="text-[12.5px] leading-relaxed text-muted-foreground">{step}</span>
            </li>
          ))}
        </ol>

        <div className="mt-5 flex items-center gap-2">
          <Button type="button" onClick={handleCopy} className="flex-1">
            {/* Both icons occupy the same cell so the label never shifts on
                the swap — the check cross-fades in place. */}
            <span className="relative inline-flex size-4 items-center justify-center">
              <Copy
                className={cn(
                  "absolute size-4 transition-all duration-200",
                  copied ? "scale-50 opacity-0" : "scale-100 opacity-100",
                )}
              />
              <Check
                className={cn(
                  "absolute size-4 transition-all duration-200",
                  copied ? "scale-100 opacity-100" : "scale-50 opacity-0",
                )}
              />
            </span>
            {copied ? "Copied" : copyLabel}
          </Button>

          <Button
            type="button"
            variant="outline"
            size="icon"
            aria-expanded={open}
            aria-label={open ? `Hide the full ${title}` : `Show the full ${title}`}
            onClick={() => setOpen((value) => !value)}
          >
            <ChevronDown className={cn("size-4 transition-transform duration-300", open && "rotate-180")} />
          </Button>
        </div>

        {/* grid-rows 0fr → 1fr is the only way to transition to an unknown
            content height without measuring it in JS. */}
        <div
          className={cn(
            "grid transition-[grid-template-rows,opacity] duration-300 ease-out",
            open ? "mt-4 grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
          )}
        >
          <div className="overflow-hidden">
            <div className="flex items-center justify-between gap-3 pb-2 text-[11px] text-muted-foreground">
              <span>Full prompt</span>
              <span className="font-mono">{lineCount} lines</span>
            </div>
            <pre
              tabIndex={open ? 0 : -1}
              aria-hidden={!open}
              aria-label={`${title} text`}
              className="max-h-64 overflow-auto rounded-lg border border-border bg-background px-3.5 py-3 font-mono text-[11.5px] leading-6 whitespace-pre-wrap text-muted-foreground"
            >
              {value}
            </pre>
          </div>
        </div>
      </div>
    </section>
  );
}
