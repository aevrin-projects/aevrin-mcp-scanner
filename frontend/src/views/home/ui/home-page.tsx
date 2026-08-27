import Link from "next/link";
import { headers } from "next/headers";
import {
  ArrowRight,
  Blocks,
  Bot,
  Eye,
  KeyRound,
  PackageOpen,
  Plug,
  ScanSearch,
  ShieldAlert,
  TerminalSquare,
  Users,
} from "lucide-react";
import { SiteFooter } from "@/widgets/site-footer";
import { Reveal } from "@/shared/ui/reveal";
import { HeroGraphic } from "./hero-graphic";

/* The scanners Aevrin actually runs, taken from ToolName in scanner-core.
   The reference design fills this slot with customer logos. Aevrin has no
   customers it can name, and inventing a logo wall would be fabricated social
   proof on a security product. The honest object with the same job is the set
   of established tools it delegates to, which is also the credibility claim
   the whole product rests on. */
const SCANNERS = [
  "Semgrep",
  "Bandit",
  "Gitleaks",
  "TruffleHog",
  "OSV-Scanner",
  "Trivy",
  "OpenSSF Scorecard",
  "MCP-Shield",
  "mcp-scan",
  "MCP Context Protector",
];

/* Every surface here exists and is reachable in the signed-in product. */
const SURFACES = [
  { icon: ScanSearch, name: "Scanning", note: "Repository, live server, local folder, pasted config" },
  { icon: Bot, name: "Agent posture", note: "Claude Code and Codex, per device" },
  { icon: Blocks, name: "MCP inventory", note: "Every server, graded A to D" },
  { icon: ShieldAlert, name: "Attack paths", note: "Only where there is evidence for each step" },
  { icon: Users, name: "Workspaces", note: "Invite people, write your own roles" },
  { icon: Plug, name: "Hooks and CI", note: "Block a bad install, fail a build" },
];

const PILLARS = [
  {
    icon: ScanSearch,
    title: "Scan before you install",
    body: "Point Aevrin at a repository, a live MCP server, a local folder, or a pasted config. Ten open-source scanners run, and the findings come back mapped to OWASP MCP categories with a trust grade from A to D.",
    href: "/docs/targets",
  },
  {
    icon: Bot,
    title: "See what your agents may already do",
    body: "One command reports what Claude Code and Codex have been allowed to do on a machine: permissions, MCP servers, skills, hooks, and which credentials sit within reach of a shell.",
    href: "/docs/agent-posture",
  },
  {
    icon: Users,
    title: "Share it with your team",
    body: "A workspace shares scans, agents and findings with the people in it. Invite by email, and decide what each role may do from a fixed catalogue the server enforces.",
    href: "/docs/dashboard",
  },
  {
    icon: Plug,
    title: "Stop it at the door",
    body: "The Claude Code hook blocks an install that has unresolved critical or high findings. In CI, exit code 1 is a finding at your threshold and 3 is incomplete coverage, which never passes as clean.",
    href: "/docs/ci",
  },
];

/* Concrete failure modes, each tied to a category the scanner really checks.
   This is a risk explanation, not a feature list. */
const RISKS = [
  {
    icon: Eye,
    title: "It ships a description the model obeys",
    body: "A tool description is instructions to your agent. Text hidden inside it can redirect behaviour without ever touching your code.",
    tag: "MCP02 Tool poisoning",
  },
  {
    icon: KeyRound,
    title: "It runs with your credentials",
    body: "Servers routinely hold tokens for the systems they reach. A leaked or over-scoped credential inherits everything you granted.",
    tag: "MCP01 Token mismanagement",
  },
  {
    icon: TerminalSquare,
    title: "It executes on your machine",
    body: "A stdio server is a local process. An unescaped argument reaching a shell is command execution on the host.",
    tag: "MCP05 Command injection",
  },
  {
    icon: PackageOpen,
    title: "It can change after you trust it",
    body: "Tool definitions drift after install, and dependencies carry their own known vulnerabilities.",
    tag: "MCP04 Rug pull",
  },
];

const EXIT_CODES = [
  { code: "0", meaning: "Complete scan, nothing at or above your threshold" },
  { code: "1", meaning: "Complete scan, something at or above it" },
  { code: "2", meaning: "Could not start: auth, quota, or an unreachable target" },
  { code: "3", meaning: "Ran, but coverage was incomplete. Never a pass" },
];

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <p className="mk-eyebrow">{children}</p>;
}

export async function LandingPage() {
  const headersList = await headers();
  const signedIn = Boolean(headersList.get("x-aevrin-user-email"));
  const primaryHref = signedIn ? "/dashboard" : "/login";

  return (
    <div className="marketing">
      {/* ---------------------------------------------------------------- Hero */}
      <section className="relative overflow-hidden bg-white">
        <div
          className="mk-dots pointer-events-none absolute inset-y-0 right-0 hidden w-1/2 text-[color:var(--mk-line)] lg:block"
          aria-hidden="true"
        />
        <div className="relative mx-auto grid max-w-[1240px] items-center gap-14 px-6 pt-16 pb-20 lg:grid-cols-[1.05fr_1fr] lg:px-10 lg:pt-24 lg:pb-24">
          <div>
            <Reveal>
              <Eyebrow>MCP and AI agent security</Eyebrow>
            </Reveal>
            <Reveal delay={60}>
              <h1 className="mk-display mt-5 text-balance">
                <span style={{ color: "var(--mk-accent)" }}>Know what it can do</span> before you
                install it.
              </h1>
            </Reveal>
            <Reveal delay={120}>
              <p className="mt-6 max-w-xl text-lg leading-relaxed text-[color:var(--mk-muted)]">
                Aevrin scans MCP servers with established open-source security tools, then reports
                what it found, what it could not check, and how to fix it. It also tells you what
                the AI agents on your machines have already been allowed to do.
              </p>
            </Reveal>
            <Reveal delay={180}>
              <div className="mt-9 flex flex-col gap-3 sm:flex-row">
                <Link
                  href={primaryHref}
                  className="inline-flex h-12 items-center justify-center gap-2 rounded-[4px] bg-[color:var(--mk-accent)] px-7 text-[15px] font-medium text-white transition-opacity hover:opacity-90"
                >
                  {signedIn ? "Open the dashboard" : "Start free"}
                  <ArrowRight className="size-4" />
                </Link>
                <Link
                  href="/docs/installation"
                  className="inline-flex h-12 items-center justify-center rounded-[4px] bg-[color:var(--mk-ink)] px-7 text-[15px] font-medium text-white transition-opacity hover:opacity-90"
                >
                  Install the CLI
                </Link>
              </div>
            </Reveal>
            <Reveal delay={240}>
              <p className="mt-6 text-[13px] text-[color:var(--mk-muted)]">
                Free plan needs no card. Nothing renews automatically.
              </p>
            </Reveal>
          </div>

          <Reveal delay={140}>
            <HeroGraphic />
          </Reveal>
        </div>
      </section>

      {/* ------------------------------------------------------- Scanner band */}
      <section className="border-b border-white/10 bg-[color:var(--mk-deep)] py-16">
        <div className="mx-auto max-w-[1240px] px-6 lg:px-10">
          <p className="mk-mono text-center text-[12px] tracking-[0.16em] text-[color:var(--mk-onDark)]/55 uppercase">
            Ten open-source scanners, none of them ours
          </p>
          <div className="mx-auto mt-8 flex max-w-4xl flex-wrap items-center justify-center gap-x-9 gap-y-4">
            {SCANNERS.map((name) => (
              <span key={name} className="text-[15px] font-medium text-[color:var(--mk-onDark)]/70">
                {name}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------- Platform */}
      <section className="bg-[color:var(--mk-deep)] pt-24 pb-24">
        <div className="mx-auto max-w-[1240px] px-6 lg:px-10">
          <Reveal>
            <h2 className="mk-h2 mx-auto max-w-3xl text-center text-balance text-white">
              One place for what your agents run, and what it can reach
            </h2>
          </Reveal>

          {/* Real anchors. A row of pills that filtered nothing would be a
              control that lies about what it does. */}
          <Reveal delay={80}>
            <nav className="mt-9 flex flex-wrap justify-center gap-2" aria-label="Jump to a section">
              {[
                { label: "Platform", href: "#platform" },
                { label: "Scanning", href: "#capabilities" },
                { label: "Agent posture", href: "#capabilities" },
                { label: "Workspaces", href: "#capabilities" },
                { label: "The risk", href: "#risk" },
                { label: "Coverage", href: "#coverage" },
              ].map((tab, index) => (
                <Link
                  key={tab.label}
                  href={tab.href}
                  className={
                    index === 0
                      ? "rounded-full bg-white px-5 py-2 text-[14px] font-medium text-[color:var(--mk-ink)]"
                      : "rounded-full bg-white/[0.07] px-5 py-2 text-[14px] text-[color:var(--mk-onDark)]/80 transition-colors hover:bg-white/[0.13]"
                  }
                >
                  {tab.label}
                </Link>
              ))}
            </nav>
          </Reveal>

          <Reveal delay={140}>
            <div
              id="platform"
              className="mt-12 grid scroll-mt-24 gap-10 bg-[color:var(--mk-panel)] p-10 lg:grid-cols-[1fr_1.15fr] lg:p-14"
            >
              <div className="flex flex-col">
                <h3 className="mk-h3 text-[26px] leading-tight">The Aevrin platform</h3>
                <p className="mt-4 max-w-md text-[15px] leading-relaxed text-[color:var(--mk-ink)]/70">
                  Scanning and agent posture in one account. What a server is, what it scored, which
                  machines load it, and what the agent loading it is allowed to do.
                </p>
                <Link
                  href={primaryHref}
                  className="mt-8 inline-flex h-11 w-fit items-center gap-2 rounded-[4px] bg-[color:var(--mk-accent)] px-6 pt-[1px] text-[14px] font-medium text-white transition-opacity hover:opacity-90"
                >
                  Explore the platform
                  <ArrowRight className="size-4" />
                </Link>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {SURFACES.map((surface) => (
                  <div
                    key={surface.name}
                    className="flex flex-col rounded-[4px] bg-white p-4 shadow-[0_1px_2px_rgba(27,49,57,0.06)]"
                  >
                    <span className="flex size-9 items-center justify-center rounded-[8px] bg-[color:var(--mk-accent)]/10">
                      <surface.icon
                        className="size-[18px] text-[color:var(--mk-accent)]"
                        aria-hidden="true"
                      />
                    </span>
                    <span className="mt-3 text-[14px] font-medium">{surface.name}</span>
                    <span className="mt-1 text-[12px] leading-snug text-[color:var(--mk-ink)]/55">
                      {surface.note}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ------------------------------------------------------ Capabilities */}
      <section id="capabilities" className="scroll-mt-20 bg-[color:var(--mk-deep)] pb-24">
        <div className="mx-auto max-w-[1240px] px-6 lg:px-10">
          <Reveal>
            <p className="mk-mono text-[12px] tracking-[0.16em] text-[color:var(--mk-accent-bright)] uppercase">
              What you get
            </p>
          </Reveal>
          <div className="mt-8 grid gap-px bg-white/10 sm:grid-cols-2 lg:grid-cols-4">
            {PILLARS.map((pillar, index) => (
              <Reveal key={pillar.title} delay={index * 60}>
                <Link
                  href={pillar.href}
                  className="group flex h-full flex-col bg-[color:var(--mk-deep)] p-7 transition-colors hover:bg-white/[0.04]"
                >
                  <span className="flex size-11 items-center justify-center rounded-[10px] bg-[color:var(--mk-accent)]/15">
                    <pillar.icon
                      className="size-5 text-[color:var(--mk-accent-bright)]"
                      aria-hidden="true"
                    />
                  </span>
                  <span className="mt-5 flex items-center gap-2 text-[17px] font-medium text-white">
                    {pillar.title}
                    <ArrowRight
                      className="size-4 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
                      aria-hidden="true"
                    />
                  </span>
                  <span className="mt-3 text-[14px] leading-relaxed text-[color:var(--mk-onDark)]/60">
                    {pillar.body}
                  </span>
                </Link>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------------- Risk */}
      <section id="risk" className="scroll-mt-20 bg-[color:var(--mk-cream)] py-24">
        <div className="mx-auto max-w-[1240px] px-6 lg:px-10">
          <Reveal className="mx-auto max-w-3xl text-center">
            <Eyebrow>The risk</Eyebrow>
            <h2 className="mk-h2 mt-4 text-balance">
              An MCP server is code, credentials, and instructions your agent trusts
            </h2>
            <p className="mt-4 text-[15px] leading-relaxed text-[color:var(--mk-ink)]/65">
              Installing one grants real capability on your machine and in the systems it reaches.
              These are the failure modes Aevrin looks for.
            </p>
          </Reveal>

          <div className="mt-14 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {RISKS.map((risk, index) => (
              <Reveal key={risk.title} delay={index * 60}>
                <div className="flex h-full flex-col border-t border-[color:var(--mk-line)] pt-6">
                  <risk.icon
                    className="size-5 text-[color:var(--mk-accent)]"
                    aria-hidden="true"
                  />
                  <h3 className="mk-h3 mt-4 text-[17px] text-balance">{risk.title}</h3>
                  <p className="mt-3 flex-1 text-[14px] leading-relaxed text-[color:var(--mk-ink)]/65">
                    {risk.body}
                  </p>
                  <span className="mk-mono mt-5 text-[11px] tracking-wider text-[color:var(--mk-ink)]/45 uppercase">
                    {risk.tag}
                  </span>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------- Coverage */}
      <section id="coverage" className="scroll-mt-20 bg-white py-24">
        <div className="mx-auto grid max-w-[1240px] gap-14 px-6 lg:grid-cols-2 lg:px-10">
          <Reveal>
            <Eyebrow>Honest coverage</Eyebrow>
            <h2 className="mk-h2 mt-4 text-balance">
              A clean result never quietly means we did not look
            </h2>
            <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-[color:var(--mk-ink)]/65">
              If a scanner fails, a stage is skipped, or a target cannot be source-scanned, the
              result says so: on the page, in the CLI, and in the exported report. Partial coverage
              stays labelled partial instead of being rounded up to a passing score.
            </p>
            <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-[color:var(--mk-ink)]/65">
              That is why the build has a separate exit code for it. An environment too broken to
              scan is not a pass at any threshold.
            </p>
          </Reveal>

          <Reveal delay={100}>
            <div className="border-t border-[color:var(--mk-line)]">
              {EXIT_CODES.map((row) => (
                <div
                  key={row.code}
                  className="flex items-baseline gap-6 border-b border-[color:var(--mk-line)] py-5"
                >
                  <span className="mk-mono w-8 shrink-0 text-[28px] leading-none font-medium text-[color:var(--mk-accent)]">
                    {row.code}
                  </span>
                  <span className="text-[15px] leading-relaxed text-[color:var(--mk-ink)]/80">
                    {row.meaning}
                  </span>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* --------------------------------------------------------------- CTA */}
      <section className="bg-[color:var(--mk-ink)] py-24">
        <div className="mx-auto max-w-[1240px] px-6 text-center lg:px-10">
          <Reveal>
            <h2 className="mk-h2 mx-auto max-w-2xl text-balance text-white">
              Find out what you have already installed
            </h2>
            <p className="mx-auto mt-5 max-w-xl text-[15px] leading-relaxed text-[color:var(--mk-onDark)]/65">
              Run one command and see every MCP server your agents load, on every machine you use.
            </p>
            <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link
                href={primaryHref}
                className="inline-flex h-12 items-center justify-center gap-2 rounded-[4px] bg-white px-7 text-[15px] font-medium text-[color:var(--mk-ink)] transition-opacity hover:opacity-90"
              >
                {signedIn ? "Open the dashboard" : "Start free"}
                <ArrowRight className="size-4" />
              </Link>
              <Link
                href="/pricing"
                className="inline-flex h-12 items-center justify-center rounded-[4px] border border-white/25 px-7 text-[15px] font-medium text-white transition-colors hover:bg-white/10"
              >
                See pricing
              </Link>
            </div>
            <p className="mk-mono mt-10 text-[13px] text-[color:var(--mk-onDark)]/50">
              pipx install aevrin
            </p>
          </Reveal>
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}
