"use client";

import { CopyButton } from "@/shared/ui/copy-button";
import { Reveal } from "@/shared/ui/reveal";
import { Card, CardContent } from "@/shared/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import { AGENT_HOOK_PROMPT, AGENT_INSTALL_PROMPT, CLI_INSTALL_COMMANDS, CLI_VERIFY_COMMANDS } from "@/shared/config/cli-commands";

export function InstallDocsSection({ headingLevel = "h2" }: { headingLevel?: "h1" | "h2" }) {
  const Heading = headingLevel;
  return (
    <section id="install" className="border-t border-border/80 bg-muted/10">
      <div className="mx-auto max-w-[1500px] px-6 py-24 lg:px-10 xl:px-14">
        <div className="grid items-start gap-8 xl:grid-cols-[1.12fr_0.88fr]">
          <div className="space-y-6">
            <Reveal>
              <span className="text-xs font-medium tracking-wide text-brand-text uppercase">Install and verify</span>
              <Heading className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
                Set up Aevrin from a real terminal, not a marketing checklist.
              </Heading>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground sm:text-base">
                Use the exact commands the current product supports. Device login is the default
                path for developers. API keys are for CI and other non-interactive automation.
              </p>
            </Reveal>

            <Reveal delay={90}>
              <Tabs defaultValue={CLI_INSTALL_COMMANDS[0].id} className="w-full">
                <TabsList className="grid h-auto w-full grid-cols-2 rounded-xl bg-background/80 p-1 sm:grid-cols-4">
                  {CLI_INSTALL_COMMANDS.map((item) => (
                    <TabsTrigger key={item.id} value={item.id}>
                      {item.label}
                    </TabsTrigger>
                  ))}
                </TabsList>
                {CLI_INSTALL_COMMANDS.map((item) => (
                  <TabsContent key={item.id} value={item.id} className="mt-4">
                    <CodePanel
                      label={`${item.label} install`}
                      value={item.value}
                      action={<CopyButton value={item.value} label="Copy commands" />}
                    />
                  </TabsContent>
                ))}
              </Tabs>
            </Reveal>

            <Reveal delay={160}>
              <CodePanel
                label="Verify and sign in"
                value={CLI_VERIFY_COMMANDS}
                action={<CopyButton value={CLI_VERIFY_COMMANDS} label="Copy verify steps" />}
              />
            </Reveal>
          </div>

          <div className="space-y-6">
            <Reveal delay={120}>
              <PromptPanel
                title="AI agent install prompt"
                description="Paste this into Claude Code or another agent when you want it to install the CLI for you."
                steps={[
                  "Detects your OS and shell: no sudo, no system Python changes",
                  "Picks npm or pipx, never both, and installs the CLI",
                  "Pauses for you to approve device login in the browser",
                  "Ends with a local scan you can run to confirm it works",
                ]}
                value={AGENT_INSTALL_PROMPT}
                label="Copy install prompt"
              />
            </Reveal>
            <Reveal delay={190}>
              <PromptPanel
                title="AI agent hook prompt"
                description="Paste this into Claude Code when you want the MCP pre-install hook configured in a project."
                steps={[
                  "Runs aevrin hook setup and waits for your device approval",
                  "Merges the PreToolUse entries into .claude/settings.json",
                  "Preserves every existing key and hook already in the file",
                  "Validates the JSON and reports exactly what it covers",
                ]}
                value={AGENT_HOOK_PROMPT}
                label="Copy hook prompt"
              />
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
}

function CodePanel({
  label,
  value,
  action,
}: {
  label: string;
  value: string;
  action?: React.ReactNode;
}) {
  return (
    <Card className="bg-background/80">
      <CardContent className="space-y-3 pt-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm font-medium text-foreground">{label}</p>
          {action}
        </div>
        <pre tabIndex={0} aria-label={`${label} code`} className="overflow-x-auto rounded-xl border border-border bg-background px-4 py-3 font-mono text-xs leading-6 text-foreground sm:text-sm">
          {value}
        </pre>
      </CardContent>
    </Card>
  );
}

/** These prompts run to ~40 lines each. Rendering them in full turned a
 *  polished section into two walls of monospace nobody reads, the only
 *  action anyone takes here is "copy". So: show what it will do as a short
 *  numbered summary, keep copy as the primary action, and put the raw text
 *  behind a disclosure for the people who genuinely want to read it first. */
function PromptPanel({
  title,
  description,
  steps,
  value,
  label,
}: {
  title: string;
  description: string;
  steps: string[];
  value: string;
  label: string;
}) {
  const lineCount = value.trim().split("\n").length;

  return (
    <Card className="bg-background/80">
      <CardContent className="space-y-4 pt-5">
        <div className="space-y-2">
          <p className="text-base font-medium text-foreground">{title}</p>
          <p className="text-sm leading-6 text-muted-foreground">{description}</p>
        </div>

        <ol className="space-y-2.5">
          {steps.map((step, index) => (
            <li key={step} className="flex items-start gap-2.5">
              <span className="mt-px flex size-4.5 shrink-0 items-center justify-center rounded-full border border-border font-mono text-[10px] text-muted-foreground">
                {index + 1}
              </span>
              <span className="text-[13px] leading-relaxed text-muted-foreground">{step}</span>
            </li>
          ))}
        </ol>

        <div className="flex flex-wrap items-center gap-3">
          <CopyButton value={value} label={label} />
          <span className="text-[11px] text-muted-foreground">{lineCount} lines</span>
        </div>

        <details className="group">
          <summary className="cursor-pointer list-none text-[12px] text-muted-foreground transition-colors hover:text-foreground">
            <span className="group-open:hidden">Show full prompt</span>
            <span className="hidden group-open:inline">Hide full prompt</span>
          </summary>
          <pre
            tabIndex={0}
            aria-label={`${title} text`}
            className="mt-3 max-h-72 overflow-auto rounded-xl border border-border bg-background px-4 py-3 font-mono text-xs leading-6 whitespace-pre-wrap text-muted-foreground"
          >
            {value}
          </pre>
        </details>
      </CardContent>
    </Card>
  );
}
