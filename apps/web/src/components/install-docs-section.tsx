"use client";

import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Copy, Check } from "lucide-react";
import { Reveal } from "@/components/reveal";

// pipx first — a bare `pip install` fails on modern Debian/Ubuntu and
// Homebrew Python with "externally-managed-environment" unless you pass
// --break-system-packages or use a venv. pipx sidesteps that by giving the
// CLI its own isolated environment automatically, which is also just the
// correct way to install a Python CLI tool regardless. Requires Python 3.10+.
const OS_INSTALL: Record<string, string> = {
  macos: "brew install pipx\npipx ensurepath\npipx install aevrin",
  windows: "py -m pip install --user pipx\npy -m pipx ensurepath\npipx install aevrin",
  linux: "python3 -m pip install --user pipx\npython3 -m pipx ensurepath\npipx install aevrin",
};

const PIP_FALLBACK = "pip install aevrin";

const VERIFY_BLOCK = "aevrin --version      # confirms the install worked\naevrin login          # opens the device-flow login in your browser";

const HOOK_PROMPT = `Install and configure the Aevrin MCP security hook in this project.
Run \`aevrin hook setup\`, complete the login flow it opens, then add the
PreToolUse hook it generates to my Claude Code settings so any \`claude mcp add\`
or edit to .mcp.json / claude_desktop_config.json is checked against Aevrin
before the install completes.`;

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      {copied ? "Copied" : label}
    </Button>
  );
}

export function InstallDocsSection() {
  return (
    <section id="install" className="mx-auto max-w-3xl px-6 py-20">
      <Reveal>
        <span className="text-xs font-medium tracking-wide text-brand uppercase">Get started</span>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
          Install the CLI, then log in.
        </h2>
      </Reveal>

      <Tabs defaultValue="macos" className="mt-8">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="macos">macOS</TabsTrigger>
          <TabsTrigger value="windows">Windows</TabsTrigger>
          <TabsTrigger value="linux">Linux</TabsTrigger>
        </TabsList>
        {(["macos", "windows", "linux"] as const).map((os) => (
          <TabsContent key={os} value={os} className="mt-4">
            <div className="flex items-start justify-between gap-4 rounded-lg border border-border bg-muted/40 p-4">
              <pre className="overflow-x-auto text-sm">
                <code>{OS_INSTALL[os]}</code>
              </pre>
              <CopyButton text={OS_INSTALL[os]} label="Copy" />
            </div>
          </TabsContent>
        ))}
      </Tabs>

      <p className="mt-4 text-sm text-muted-foreground">
        Already have pipx, or prefer a plain venv? <code className="text-foreground">{PIP_FALLBACK}</code> works
        too. Requires Python 3.10+.
      </p>

      <div className="mt-6 rounded-lg border border-border bg-muted/40 p-4">
        <pre className="overflow-x-auto text-sm">
          <code>{VERIFY_BLOCK}</code>
        </pre>
      </div>

      <div className="mt-10">
        <h3 className="text-lg font-medium">Claude Code hook</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Paste this directly into a Claude Code conversation — it&apos;s not a shell command.
        </p>
        <div className="mt-3 flex items-start justify-between gap-4 rounded-lg border border-border bg-muted/40 p-4">
          <pre className="overflow-x-auto whitespace-pre-wrap text-sm">
            <code>{HOOK_PROMPT}</code>
          </pre>
          <CopyButton text={HOOK_PROMPT} label="Copy prompt" />
        </div>
      </div>
    </section>
  );
}
