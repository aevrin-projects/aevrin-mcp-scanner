"use client";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/shared/ui/accordion";
import { Reveal } from "@/shared/ui/reveal";

/**
 * Folio's FAQ layout: a sticky index of groups on the left, accordion groups
 * on the right, the open item lifted onto a card and closed ones separated by
 * hairlines.
 *
 * Only questions with a documented answer. Billing answers follow the app's
 * own pricing FAQ (frontend/src/widgets/pricing); scanning, hook, registry and
 * posture answers follow docs/features/*.md and docs/reference/CLI.md.
 */

type Group = { id: string; title: string; items: { q: string; a: string }[] };

const GROUPS: Group[] = [
  {
    id: "faq-scanning",
    title: "Scanning",
    items: [
      {
        q: "What does a scan actually check?",
        a: "Aevrin starts the server in a disposable container, completes the MCP handshake and runs its rules over every tool the server declares: tool poisoning, excessive permissions, secrets passed as arguments, known compromised packages, install-time scripts and more. It reads tool definitions, not runtime behaviour, so a grade describes one version at one moment.",
      },
      {
        q: "What does Incomplete mean?",
        a: "One of the five stages could not finish, most often because the server would not start without credentials of its own. The report names the stage and the reason and gives no grade. Incomplete is never treated as clean, and the CLI exits with code 3.",
      },
      {
        q: "Which OWASP MCP Top 10 categories are covered?",
        a: "Seven: MCP01, MCP02, MCP03, MCP04, MCP05, MCP07 and MCP09. MCP08, prompt injection via live tool responses, needs dynamic testing against a live server and is not tested; every report says so. MCP06 and MCP10 have no rule.",
      },
      {
        q: "Can an AI explanation change a grade?",
        a: "No. An explanation interprets the evidence the scan collected and never detects anything, so a finding or a grade never changes because of what a model said. Explanations run on your own Groq, OpenAI, Anthropic or Google Gemini key and see only an allow-listed summary of the scan, never your source code or environment.",
      },
    ],
  },
  {
    id: "faq-agents",
    title: "Agents and the registry",
    items: [
      {
        q: "What does the Claude Code hook do?",
        a: "When Claude Code runs claude mcp add or writes .mcp.json, the hook asks Aevrin for that server's last scan. Unresolved critical or high findings deny the install and hand your agent the findings and three options: fix it, allow it for ten minutes, or dispute a finding. A server with no scan is allowed while one is queued, and if Aevrin cannot be reached the hook allows the install. Servers added by URL scan fully; one started by a local command currently ends Incomplete.",
      },
      {
        q: "Does agent posture send my configuration anywhere?",
        a: "Not unless you ask. aevrin agent scan reads Claude Code and Codex configuration on your machine and executes nothing. The report stays local unless you pass --upload, and an upload carries metadata about credentials, never their values.",
      },
      {
        q: "Is a registry listing a security verdict?",
        a: "No. The registry is for discovery, and no listing carries a grade or a scan result. Scan a server you found before you install it.",
      },
    ],
  },
  {
    id: "faq-billing",
    title: "Plans and billing",
    items: [
      {
        q: "Is a card required for the Free plan?",
        a: "No. Free needs only an account, no billing information at all.",
      },
      {
        q: "Does a paid plan renew automatically?",
        a: "No. Each checkout buys one monthly or annual cycle. The account returns to Free after the paid-until date unless you buy another cycle.",
      },
      {
        q: "What happens when I reach a limit?",
        a: "That bucket pauses until it resets on your rolling monthly cycle, or until you upgrade. CLI, hook, dashboard and agent scans are counted separately, and each surface tells you which one ran out and when it resets.",
      },
      {
        q: "How does Team work?",
        a: "Team is billed per seat, from 3 to 500 seats, and the workspace owner buys it. Everyone in the workspace gets Team limits while it is active, and members see the workspace's scans, findings and agents. Personal scans stay private. You invite people by email and decide what each role may do.",
      },
    ],
  },
];

export function Faq() {
  return (
    <section id="faq" aria-labelledby="faq-title" className="mk-section">
      <div className="mk-container grid gap-10 md:grid-cols-5 md:gap-12">
        <Reveal className="md:col-span-2">
          <div className="md:sticky md:top-28">
            <h2 id="faq-title" className="mk-h2">
              Questions
            </h2>
            <p className="mt-4 max-w-xs text-[15px] leading-6 text-[var(--mk-muted)]">
              Something not answered here?{" "}
              <a
                href="mailto:support@aevrin.net"
                className="font-medium text-[var(--mk-fg)] underline decoration-[var(--mk-line-strong)] underline-offset-4 hover:decoration-current"
              >
                Write to support
              </a>
              .
            </p>
            <nav aria-label="Question groups" className="mt-8 hidden md:block">
              <ul className="space-y-2.5 text-sm">
                {GROUPS.map((group) => (
                  <li key={group.id}>
                    <a
                      href={`#${group.id}`}
                      className="rounded-sm text-[var(--mk-muted)] transition-colors hover:text-[var(--mk-fg)]"
                    >
                      {group.title}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          </div>
        </Reveal>

        <div className="space-y-12 md:col-span-3">
          {GROUPS.map((group) => (
            <Reveal key={group.id}>
              <h3 id={group.id} className="text-lg font-semibold text-[var(--mk-fg-strong)]">
                {group.title}
              </h3>
              <Accordion className="mt-4">
                {group.items.map((item) => (
                  <AccordionItem
                    key={item.q}
                    value={item.q}
                    className="rounded-xl border border-transparent border-b-[var(--mk-line)] px-4 transition-colors not-last:border-b data-[open]:border-[var(--mk-line)] data-[open]:bg-[var(--mk-surface)]"
                  >
                    <AccordionTrigger className="py-4 text-[15px] font-medium text-[var(--mk-fg-strong)] hover:no-underline">
                      {item.q}
                    </AccordionTrigger>
                    <AccordionContent className="pb-5 text-[15px] leading-7 text-[var(--mk-muted)]">
                      {item.a}
                    </AccordionContent>
                  </AccordionItem>
                ))}
              </Accordion>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
