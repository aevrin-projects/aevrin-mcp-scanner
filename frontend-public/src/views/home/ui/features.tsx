import type { ReactNode } from "react";
import { Check, Circle, Minus, Printer, TriangleAlert, X } from "lucide-react";
import { Reveal } from "@/shared/ui/reveal";
import { ScoreGauge } from "@/shared/ui/severity-charts";
import { SectionHeader } from "./section-header";

/**
 * What a scan returns, in the Nguyen bento structure (6 columns: 3 + 3, then
 * 2 + 2 + 2) with Folio's surfaces: hairline cards on the page ground, a dot
 * grid behind each mockup, and the title and description as one run of text.
 *
 * Every mockup is a representative example drawn from the product's real
 * vocabulary and is `aria-hidden`; the sentence under it states the claim.
 * Sources, so drift is findable:
 *   grades, labels, policies   backend/scanner-core/.../mcp/risk.py
 *   five stages, reasons       risk.py `_INCOMPLETE_BY_STAGE`, docs/features/MCP_SCANNING.md
 *   OWASP coverage             mcp/catalog.py rules -> classification/owasp.py
 *   exit codes                 docs/reference/CLI.md
 *   report export              docs/features/BILLING.md (`pdf_export`)
 *
 * This replaces the "product facts" and "platform" sections, which claimed
 * ten scanners, nine OWASP categories, six stages, grades from A to D, file
 * and line on every finding, an attack-path model the code does not build,
 * and shared workspaces before they existed.
 */

const TARGET = "github.com/owner/notes-mcp";

function MockFrame({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`overflow-hidden rounded-xl border border-[var(--mk-line)] bg-[var(--mk-surface)] shadow-lg shadow-black/5 ${className}`}
    >
      {children}
    </div>
  );
}

const GRADES = [
  { letter: "A", label: "Trusted", policy: "Allow" },
  { letter: "B", label: "Generally safe", policy: "Allow" },
  { letter: "C", label: "Caution", policy: "Require approval" },
  { letter: "D", label: "High risk", policy: "Require approval" },
  { letter: "F", label: "Do not use", policy: "Block" },
];

function GradeMock() {
  return (
    <MockFrame className="w-full max-w-[440px]">
      <div className="flex items-center justify-between border-b border-[var(--mk-line)] px-4 py-2.5">
        <span className="truncate font-mono text-[11px] text-[var(--mk-muted)]">{TARGET}</span>
        <span className="shrink-0 rounded-full border border-[var(--mk-line)] px-2 py-0.5 text-[10.5px] text-[var(--mk-fg)]">
          Completed
        </span>
      </div>
      <div className="flex items-center gap-4 p-4">
        {/* `.preview-scrub` draws the gauge at its final value instead of
            playing its mount animation while it is still off screen. */}
        <div className="preview-scrub hidden shrink-0 lg:block">
          <ScoreGauge riskScore={18} size={112} />
        </div>
        <ul className="min-w-0 flex-1 space-y-1">
          {GRADES.map((grade) => {
            const active = grade.letter === "B";
            return (
              <li
                key={grade.letter}
                className={`flex items-center gap-2.5 rounded-md px-2 py-1 text-[11.5px] ${
                  active ? "bg-[var(--mk-hover)] text-[var(--mk-fg-strong)]" : "text-[var(--mk-muted)]"
                }`}
              >
                <span
                  className={`grid size-5 shrink-0 place-items-center rounded font-mono text-[11px] font-semibold ${
                    active
                      ? "bg-[var(--mk-primary)] text-[var(--mk-primary-fg)]"
                      : "border border-[var(--mk-line)]"
                  }`}
                >
                  {grade.letter}
                </span>
                <span className="truncate">{grade.label}</span>
                <span className="ml-auto shrink-0 font-mono text-[10px]">{grade.policy}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </MockFrame>
  );
}

const STAGES: { name: string; state: "done" | "stopped" | "skipped" }[] = [
  { name: "resolving", state: "done" },
  { name: "launching", state: "stopped" },
  { name: "enumerating", state: "skipped" },
  { name: "analyzing", state: "skipped" },
  { name: "grading", state: "skipped" },
];

function CoverageMock() {
  return (
    <MockFrame className="w-full max-w-[440px]">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--mk-line)] px-4 py-2.5">
        <span className="truncate font-mono text-[11px] text-[var(--mk-muted)]">{TARGET}</span>
        <span className="flex shrink-0 items-center gap-1 rounded-full border border-[var(--mk-line)] px-2 py-0.5 text-[10.5px] text-severity-high">
          <TriangleAlert className="size-3" />
          Incomplete, no grade
        </span>
      </div>
      <ol className="px-4 py-2">
        {STAGES.map((stage) => (
          <li key={stage.name} className="border-b border-[var(--mk-line)] py-1.5 last:border-b-0">
            <div className="flex items-center gap-2.5 font-mono text-[11.5px]">
              {stage.state === "done" ? (
                <Check className="size-3.5 text-[var(--mk-fg)]" />
              ) : stage.state === "stopped" ? (
                <X className="size-3.5 text-severity-high" />
              ) : (
                <Circle className="size-3 text-[var(--mk-muted)]" />
              )}
              <span className={stage.state === "skipped" ? "text-[var(--mk-muted)]" : "text-[var(--mk-fg)]"}>
                {stage.name}
              </span>
              <span className="ml-auto text-[10.5px] text-[var(--mk-muted)]">
                {stage.state === "done" ? "done" : stage.state === "stopped" ? "stopped here" : "not reached"}
              </span>
            </div>
            {stage.state === "stopped" ? (
              <p className="mt-1 ml-6 text-[11px] leading-4 text-[var(--mk-fg)]">
                The server was identified but could not be started, so its tools were never read.
              </p>
            ) : null}
          </li>
        ))}
      </ol>
    </MockFrame>
  );
}

// The seven categories the rules map to, and the three they do not.
const OWASP: { code: string; state: "covered" | "not-tested" | "no-rule" }[] = [
  { code: "MCP01", state: "covered" },
  { code: "MCP02", state: "covered" },
  { code: "MCP03", state: "covered" },
  { code: "MCP04", state: "covered" },
  { code: "MCP05", state: "covered" },
  { code: "MCP06", state: "no-rule" },
  { code: "MCP07", state: "covered" },
  { code: "MCP08", state: "not-tested" },
  { code: "MCP09", state: "covered" },
  { code: "MCP10", state: "no-rule" },
];

function OwaspMock() {
  return (
    <div className="w-full max-w-[300px]">
      <ul className="grid grid-cols-5 gap-1.5">
        {OWASP.map((item) => (
          <li
            key={item.code}
            className={`flex flex-col items-center gap-1 rounded-lg border py-2 font-mono text-[10px] ${
              item.state === "covered"
                ? "border-[var(--mk-line)] bg-[var(--mk-surface)] text-[var(--mk-fg)]"
                : item.state === "not-tested"
                  ? "border-dashed border-severity-medium bg-[var(--mk-surface)] text-[var(--mk-fg)]"
                  : "border-dashed border-[var(--mk-line-strong)] text-[var(--mk-muted)]"
            }`}
          >
            {item.state === "covered" ? (
              <Check className="size-3" />
            ) : item.state === "not-tested" ? (
              <TriangleAlert className="size-3 text-severity-medium" />
            ) : (
              <Minus className="size-3" />
            )}
            {item.code.replace("MCP", "")}
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap justify-center gap-x-3 gap-y-1 text-[10.5px] text-[var(--mk-muted)]">
        <span>7 covered</span>
        <span>MCP08 not tested</span>
        <span>2 no rule</span>
      </div>
    </div>
  );
}

const EXIT_CODES = [
  { code: "0", meaning: "clean" },
  { code: "1", meaning: "findings at or above --fail-on" },
  { code: "2", meaning: "could not start" },
  { code: "3", meaning: "incomplete" },
];

function ExitMock() {
  return (
    <MockFrame className="w-full max-w-[320px]">
      <div className="flex items-center gap-1.5 border-b border-[var(--mk-line)] px-3 py-2">
        <span className="size-2 rounded-full bg-[var(--mk-line-strong)]" />
        <span className="size-2 rounded-full bg-[var(--mk-line-strong)]" />
        <span className="size-2 rounded-full bg-[var(--mk-line-strong)]" />
      </div>
      <div className="space-y-1 px-3.5 py-3 font-mono text-[11px] leading-[1.5]">
        <p className="truncate text-[var(--mk-fg)]">
          <span className="text-[var(--mk-muted)]">$</span> aevrin scan . --fail-on high
        </p>
        <p className="truncate text-[var(--mk-muted)]">Grade D, 2 high findings</p>
        <ul className="mt-2 border-t border-[var(--mk-line)] pt-2">
          {EXIT_CODES.map((row) => (
            <li
              key={row.code}
              className={`flex gap-2 rounded px-1 ${
                row.code === "1" ? "-mx-0 bg-[var(--mk-hover)] text-[var(--mk-fg-strong)]" : "text-[var(--mk-muted)]"
              }`}
            >
              <span>exit {row.code}</span>
              <span className="truncate">{row.meaning}</span>
            </li>
          ))}
        </ul>
      </div>
    </MockFrame>
  );
}

function Bar({ width }: { width: string }) {
  return <span className="block h-1.5 rounded-full bg-[var(--mk-line-strong)]" style={{ width }} />;
}

// A sheet rising from the bottom edge of the card, cut off on purpose.
function ReportMock() {
  return (
    <MockFrame className="w-full max-w-[300px] translate-y-6 self-end rounded-b-none border-b-0">
      <div className="flex items-start justify-between gap-3 border-b border-[var(--mk-line)] px-4 py-3">
        <div className="min-w-0">
          <p className="text-[12px] font-semibold text-[var(--mk-fg-strong)]">Security report</p>
          <p className="mt-0.5 truncate font-mono text-[10px] text-[var(--mk-muted)]">notes-mcp, grade B, risk 18/100</p>
        </div>
        <span className="flex shrink-0 items-center gap-1 rounded-md border border-[var(--mk-line)] px-1.5 py-1 text-[10px] text-[var(--mk-fg)]">
          <Printer className="size-3" />
          Print
        </span>
      </div>
      <div className="space-y-3 px-4 pt-3 pb-8">
        {["Verdict", "Findings by OWASP category", "Coverage", "Limitations"].map((heading, index) => (
          <div key={heading} className="space-y-1.5">
            <p className="text-[10.5px] font-medium text-[var(--mk-fg)]">{heading}</p>
            <Bar width={["88%", "72%", "80%", "64%"][index]} />
          </div>
        ))}
      </div>
    </MockFrame>
  );
}

const CARDS: {
  title: string;
  body: string;
  mock: ReactNode;
  span: string;
  height: string;
}[] = [
  {
    title: "A grade you can act on.",
    body: "Each server gets a letter from A to F and a risk score out of 100, where higher is worse. The server takes its worst tool's grade, with a suggested policy beside it: allow, require approval, or block.",
    mock: <GradeMock />,
    span: "lg:col-span-3",
    height: "h-[280px]",
  },
  {
    title: "Incomplete is never clean.",
    body: "A scan runs five stages. When one cannot finish, the report names the stage and the reason, and the result is Incomplete with no letter rather than a pass.",
    mock: <CoverageMock />,
    span: "lg:col-span-3",
    height: "h-[280px]",
  },
  {
    title: "Mapped to the OWASP MCP Top 10.",
    body: "Findings map to 7 of the 10 categories. MCP08, prompt injection via live tool responses, is not tested, and every report says so.",
    mock: <OwaspMock />,
    span: "lg:col-span-2",
    height: "h-[240px]",
  },
  {
    title: "Exit codes CI can branch on.",
    body: "--fail-on sets the severity that fails a build and --json returns the full result. Exit 3 means incomplete, so a partial scan cannot pass quietly.",
    mock: <ExitMock />,
    span: "lg:col-span-2",
    height: "h-[240px]",
  },
  {
    title: "A report that travels.",
    body: "Hobby, Pro and Team export a printable report. Coverage warnings stay in it, so a saved copy cannot make a partial scan look clean.",
    mock: <ReportMock />,
    span: "md:col-span-2 lg:col-span-2",
    height: "h-[240px]",
  },
];

export function Features() {
  return (
    <section id="features" aria-labelledby="features-title" className="mk-section">
      <div className="mk-container">
        <SectionHeader
          id="features-title"
          eyebrow="What a scan returns"
          title="Everything your team needs to ship AI agents safely"
          lede="Every scan grades a server from A to F, maps its findings to the OWASP MCP Top 10, and names the stage that stopped when it could not finish."
        />

        <ul className="mt-12 grid gap-4 md:mt-16 md:grid-cols-2 lg:grid-cols-6">
          {CARDS.map((card, index) => (
            <li key={card.title} className={card.span}>
              <Reveal delay={index * 100} className="h-full">
                <article className="flex h-full flex-col overflow-hidden rounded-[var(--mk-radius-card)] border border-[var(--mk-line)] bg-[var(--mk-bg)] transition-shadow duration-300 hover:shadow-lg hover:shadow-black/5">
                  <div
                    aria-hidden="true"
                    className={`mk-dots relative flex items-center justify-center overflow-hidden border-b border-[var(--mk-line)] bg-[var(--mk-illustration)] px-4 sm:px-6 ${card.height}`}
                  >
                    {card.mock}
                  </div>
                  <div className="p-5 text-[15px] leading-6 sm:p-6 sm:text-base sm:leading-7">
                    <h3 className="inline font-medium text-[var(--mk-fg-strong)]">{card.title}</h3>{" "}
                    <p className="inline text-[var(--mk-muted)]">{card.body}</p>
                  </div>
                </article>
              </Reveal>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
