"use client";

import { CopyButton } from "@/components/copy-button";
import { Reveal } from "@/components/reveal";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AGENT_HOOK_PROMPT,
  AGENT_INSTALL_PROMPT,
  CLI_INSTALL_COMMANDS,
  CLI_VERIFY_COMMANDS,
} from "@/lib/onboarding";

export function InstallDocsSection() {
  return (
    <section id="install" className="border-t border-border/80 bg-muted/10">
      <div className="mx-auto max-w-[1500px] px-6 py-24 lg:px-10 xl:px-14">
        <div className="grid gap-8 xl:grid-cols-[1.12fr_0.88fr]">
          <div className="space-y-6">
            <Reveal>
              <span className="text-xs font-medium tracking-wide text-brand uppercase">Install and verify</span>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
                Set up Aevrin from a real terminal, not a marketing checklist.
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-muted-foreground sm:text-base">
                Use the exact commands the current product supports. Device login is the default
                path for developers. API keys are for CI and other non-interactive automation.
              </p>
            </Reveal>

            <Reveal delay={90}>
              <Tabs defaultValue={CLI_INSTALL_COMMANDS[0].id} className="w-full">
                <TabsList className="grid w-full grid-cols-3 rounded-2xl bg-background/80 p-1">
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
                value={AGENT_INSTALL_PROMPT}
                label="Copy install prompt"
              />
            </Reveal>
            <Reveal delay={190}>
              <PromptPanel
                title="AI agent hook prompt"
                description="Paste this into Claude Code when you want the MCP pre-install hook configured in a project."
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
        <pre className="overflow-x-auto rounded-2xl border border-border bg-background px-4 py-3 font-mono text-xs leading-6 text-foreground sm:text-sm">
          {value}
        </pre>
      </CardContent>
    </Card>
  );
}

function PromptPanel({
  title,
  description,
  value,
  label,
}: {
  title: string;
  description: string;
  value: string;
  label: string;
}) {
  return (
    <Card className="bg-background/80">
      <CardContent className="space-y-4 pt-5">
        <div className="space-y-2">
          <p className="text-base font-medium text-foreground">{title}</p>
          <p className="text-sm leading-6 text-muted-foreground">{description}</p>
        </div>
        <pre className="overflow-x-auto rounded-2xl border border-border bg-background px-4 py-3 whitespace-pre-wrap font-mono text-xs leading-6 text-foreground sm:text-sm">
          {value}
        </pre>
        <CopyButton value={value} label={label} />
      </CardContent>
    </Card>
  );
}
