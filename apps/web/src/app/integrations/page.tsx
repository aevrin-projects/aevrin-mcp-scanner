"use client";

import { Bot, KeyRound, TerminalSquare } from "lucide-react";
import { CopyButton } from "@/components/copy-button";
import { PageHeader, SectionCard } from "@/components/product-ui";
import { Card, CardContent } from "@/components/ui/card";
import {
  AGENT_HOOK_PROMPT,
  AGENT_INSTALL_PROMPT,
  CLI_INSTALL_COMMANDS,
  CLI_VERIFY_COMMANDS,
} from "@/lib/onboarding";

export default function IntegrationsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Integrations"
        description="Install the CLI, verify sign-in, and configure the Claude Code hook with the exact flows the current product supports."
      />

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <SectionCard
          title="CLI installation"
          description="Choose the commands that match the developer machine you are setting up."
        >
          <div className="grid gap-4 lg:grid-cols-3">
            {CLI_INSTALL_COMMANDS.map((item) => (
              <CodePanel
                key={item.id}
                title={item.label}
                value={item.value}
                action={<CopyButton value={item.value} label="Copy commands" />}
              />
            ))}
          </div>
          <div className="mt-4">
            <CodePanel
              title="Verify and sign in"
              value={CLI_VERIFY_COMMANDS}
              action={<CopyButton value={CLI_VERIFY_COMMANDS} label="Copy verify steps" />}
            />
          </div>
        </SectionCard>

        <SectionCard
          title="Usage model"
          description="Use the least secret-heavy path that still fits the environment."
        >
          <div className="grid gap-4">
            <InfoCard
              title="Developer machine"
              body="Use device login with aevrin login so no long-lived secret has to live in a local shell profile."
              icon={<TerminalSquare className="size-5 text-brand" />}
            />
            <InfoCard
              title="CI or scheduled automation"
              body="Use an API key only when browser-driven device login is not practical. Generate and store it in your secret manager."
              icon={<KeyRound className="size-5 text-brand" />}
            />
            <InfoCard
              title="Claude Code hook"
              body="Use the pre-install hook when you want MCP add flows to consult Aevrin before the install completes."
              icon={<Bot className="size-5 text-brand" />}
            />
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="AI agent prompts"
        description="These are prompts to paste into Claude Code or another agent. They are not shell commands."
      >
        <div className="grid gap-4 xl:grid-cols-2">
          <PromptPanel
            title="Install prompt"
            value={AGENT_INSTALL_PROMPT}
            label="Copy install prompt"
          />
          <PromptPanel
            title="Hook prompt"
            value={AGENT_HOOK_PROMPT}
            label="Copy hook prompt"
          />
        </div>
      </SectionCard>
    </div>
  );
}

function CodePanel({
  title,
  value,
  action,
}: {
  title: string;
  value: string;
  action?: React.ReactNode;
}) {
  return (
    <Card className="bg-background/80">
      <CardContent className="space-y-3 pt-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm font-medium text-foreground">{title}</p>
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
  value,
  label,
}: {
  title: string;
  value: string;
  label: string;
}) {
  return (
    <Card className="bg-background/80">
      <CardContent className="space-y-4 pt-5">
        <div className="space-y-2">
          <p className="text-base font-medium text-foreground">{title}</p>
          <p className="text-sm leading-6 text-muted-foreground">
            Paste this into an agent when you want it to do the setup work for you.
          </p>
        </div>
        <pre className="overflow-x-auto rounded-2xl border border-border bg-background px-4 py-3 whitespace-pre-wrap font-mono text-xs leading-6 text-foreground sm:text-sm">
          {value}
        </pre>
        <CopyButton value={value} label={label} />
      </CardContent>
    </Card>
  );
}

function InfoCard({
  title,
  body,
  icon,
}: {
  title: string;
  body: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-border bg-background/80 p-4">
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-2xl border border-brand/25 bg-brand/10">
          {icon}
        </div>
        <p className="text-base font-medium text-foreground">{title}</p>
      </div>
      <p className="mt-3 text-sm leading-6 text-muted-foreground">{body}</p>
    </div>
  );
}
