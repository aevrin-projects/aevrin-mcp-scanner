import { cn } from "@/shared/lib/utils";
import { AiMockup } from "./ai-mockup";
import { GuardrailsBlock } from "./guardrails-block";
import { RegistryMockup } from "./registry-mockup";
import { SolutionBlock, type SeeAlsoLink } from "./solution-block";
import styles from "./solutions.module.css";

/*
 * Three numbered blocks in the alternating two-column structure: the
 * registry an agent can search, AI explanations, and the Claude Code hook.
 * Copy follows the design brief's section 4.10; every "See also" target is a
 * page that exists (docs.mcp.aevrin.net serves `frontend-docs/content` with
 * route groups dropped from the URL, and the app routes are in
 * `frontend/src/app`).
 */

const REGISTRY_LINKS: SeeAlsoLink[] = [
  { label: "How the registry MCP server works", href: "https://docs.mcp.aevrin.net/agents" },
  { label: "Scan a server you found", href: "https://app.mcp.aevrin.net/scans/new" },
];

const AI_LINKS: SeeAlsoLink[] = [
  { label: "What an AI explanation can and cannot do", href: "https://docs.mcp.aevrin.net/explanations" },
  { label: "Add a provider key", href: "https://docs.mcp.aevrin.net/providers" },
  { label: "Triage and false positives", href: "https://docs.mcp.aevrin.net/triage" },
];

export function SolutionBlocks() {
  return (
    <section aria-labelledby="solutions-heading" className={cn(styles.root, "py-16 md:py-28")}>
      <h2 id="solutions-heading" className="sr-only">
        Registry, AI explanations and agent guardrails
      </h2>
      <div className="mx-auto max-w-7xl space-y-20 px-4 sm:px-6 lg:space-y-28 lg:px-8">
        <SolutionBlock
          id="solution-registry"
          eyebrow="01  REGISTRY"
          title="Find it from inside your agent"
          body={
            <p>
              Add Aevrin&apos;s registry to Claude Code with one command. Your agent can search MCP
              servers, skills, prompts and templates, read one in full, and hand you its install
              config. A listing is curation, not a security verdict: scan a server before you install
              it.
            </p>
          }
          aside={
            <code
              className={cn(
                styles.mono,
                "block rounded-lg border px-3 py-2.5 text-xs leading-5 break-all",
              )}
              style={{ borderColor: "var(--mk-line)", background: "var(--mk-surface)", color: "var(--mk-fg)" }}
            >
              claude mcp add --scope user --transport http aevrin https://api.mcp.aevrin.net/mcp
            </code>
          }
          seeAlso={REGISTRY_LINKS}
          mockup={<RegistryMockup />}
        />

        <SolutionBlock
          id="solution-ai"
          eyebrow="02  AI EXPLANATIONS"
          title="Plain language, grounded in the evidence"
          body={
            <>
              <p>
                Ask why a scan earned its grade or what a finding means. The explanation uses only the
                scan&apos;s evidence, never your source code or environment, and names the provider
                and model that wrote it. Bring your own Groq, OpenAI, Anthropic or Google Gemini key.
                A finding and a grade never change because of what a model said.
              </p>
              <p>
                Every plan also gets an AI review of its findings: confirmed, likely false positive,
                or needs review.
              </p>
            </>
          }
          seeAlso={AI_LINKS}
          mockup={<AiMockup />}
          mockupFirst
        />

        <GuardrailsBlock />
      </div>
    </section>
  );
}
