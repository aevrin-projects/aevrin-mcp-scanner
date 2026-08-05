import { Bug, KeyRound, Network, ScanSearch, ShieldAlert } from "lucide-react";

// Threat classes the beam is sweeping for, as icons. These deliberately name
// what Aevrin *detects* rather than which languages it parses — a language
// mark says nothing about risk, and we have no redistribution rights to
// language trademarks anyway. Each maps to a real OWASP MCP category.
const THREATS = [
  { id: "injection", title: "Command and prompt injection", Icon: Bug, className: "left-[6%] top-[34%]", delay: "0s" },
  { id: "secrets", title: "Leaked credentials and tokens", Icon: KeyRound, className: "left-[12%] top-[68%]", delay: "1.1s" },
  { id: "perms", title: "Over-broad tool permissions", Icon: ShieldAlert, className: "right-[8%] top-[38%]", delay: "0.6s" },
  { id: "egress", title: "Unexpected network egress", Icon: Network, className: "right-[13%] top-[70%]", delay: "1.7s" },
];

/**
 * Decorative hero illustration: a scan cone sweeping a faint code field, with
 * a real finding surfacing inside the beam. Entirely aria-hidden — every
 * claim it implies is also stated in the surrounding copy, so a screen reader
 * loses nothing by skipping it.
 *
 * `overflow-hidden` is load-bearing, not cosmetic: the rings and the cone
 * carry fixed pixel sizes (up to 580px) so the beam keeps its proportions,
 * and unclipped they widened the whole document to 549px at a 320px
 * viewport — a WCAG 1.4.10 Reflow failure that forced horizontal scrolling
 * on the landing page. Clipping crops the beam at the container edge, which
 * is exactly how a spotlight should read anyway.
 */
export function HeroScanVisual() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none relative mx-auto mt-6 h-[300px] w-full max-w-4xl overflow-hidden select-none sm:h-[330px]"
    >
      {/* Faint code field the beam appears to be reading. */}
      <div className="absolute inset-x-0 top-[26%] bottom-0 overflow-hidden [mask-image:radial-gradient(ellipse_50%_60%_at_50%_35%,black,transparent_75%)]">
        <pre className="font-mono text-[10px] leading-[1.6] whitespace-pre-wrap text-foreground/[0.07] sm:text-[11px]">
          {`server.registerTool("run", { description: "Execute a task" }, async ({ cmd }) => {
  const proc = await exec(\`sh -c \${cmd}\`);            // unescaped argument
  return { content: [{ type: "text", text: proc.stdout }] };
});
server.registerTool("read", { description: "Read a file" }, async ({ p }) => {
  return fs.readFileSync(path.join(ROOT, p), "utf8");   // no normalization
});
const client = new Client({ token: process.env.API_TOKEN });
export const config = { transport: "stdio", scopes: ["fs:*", "net:*"] };
await registry.publish({ name: "mcp-notes", version: "1.4.2" });`}
        </pre>
      </div>

      {/* Concentric sonar rings, staggered so they read as successive pulses. */}
      <div className="absolute left-1/2 top-[22%] -translate-x-1/2 -translate-y-1/2">
        {[240, 360, 480].map((size, index) => (
          <div
            key={size}
            className="hero-ring absolute -translate-x-1/2 -translate-y-1/2"
            style={{ width: size, height: size, animationDelay: `${index * 1.5}s` }}
          />
        ))}
      </div>

      {/* Sweeping cone, pivoting at the hub. */}
      <div className="absolute left-1/2 top-[22%] h-[280px] w-[480px] -translate-x-1/2 sm:h-[310px] sm:w-[580px]">
        <div className="hero-scan-cone absolute inset-0" />
      </div>

      {/* Hub */}
      <div className="absolute left-1/2 top-[22%] -translate-x-1/2 -translate-y-1/2">
        <div className="flex size-14 items-center justify-center rounded-full border border-border bg-card shadow-[0_0_40px_-6px] shadow-brand/40">
          <ScanSearch className="size-5 text-brand" />
        </div>
      </div>

      {THREATS.map((threat) => (
        <div
          key={threat.id}
          title={threat.title}
          style={{ animationDelay: threat.delay }}
          className={`hero-badge absolute flex size-10 items-center justify-center rounded-lg border border-border bg-card ${threat.className}`}
        >
          <threat.Icon className="size-4 text-brand" />
        </div>
      ))}

      {/* A real finding, in the product's own shape, surfacing in the beam. */}
      <div className="hero-finding absolute bottom-[2%] left-1/2 w-[300px] max-w-[86%] -translate-x-1/2 rounded-xl border border-border bg-card p-3 shadow-2xl shadow-black/60 sm:w-[340px]">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-severity-critical" />
            <span className="text-[11px] font-medium text-foreground">Critical · MCP05</span>
          </span>
          <span className="font-mono text-[10px] text-muted-foreground">semgrep</span>
        </div>
        <p className="mt-1.5 text-[12px] leading-snug text-muted-foreground">
          Command injection via unsanitized shell argument
        </p>
        <p className="mt-1.5 font-mono text-[10px] text-muted-foreground">src/tools/run.ts:88</p>
      </div>
    </div>
  );
}
