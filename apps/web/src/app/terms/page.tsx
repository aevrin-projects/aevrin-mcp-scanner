import { SiteFooter } from "@/components/site-footer";

export default function TermsPage() {
  return (
    <div>
      <div className="mx-auto max-w-2xl px-6 py-16">
        <h1 className="text-2xl font-semibold tracking-tight">Terms of Service</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Draft — for your own legal review before this is a binding agreement. Last updated: 2026.
        </p>

        <div className="mt-8 flex flex-col gap-6 text-sm leading-relaxed text-muted-foreground">
          <section>
            <h2 className="font-medium text-foreground">The service</h2>
            <p className="mt-1">
              Aevrin scans MCP (Model Context Protocol) servers for security issues using
              established open-source tools, and reports the results to you. It does not modify,
              install, or execute the servers it scans in any way that affects your systems beyond
              the scan itself.
            </p>
          </section>
          <section>
            <h2 className="font-medium text-foreground">Accounts and usage limits</h2>
            <p className="mt-1">
              Each plan (Free, Hobby, Team) includes a fixed number of scans per month across three
              separate categories — CLI, Claude Code hook, and dashboard — that reset on a rolling
              monthly cycle from your signup date. We may adjust these limits from time to time;
              published limits at the time you use the service apply.
            </p>
          </section>
          <section>
            <h2 className="font-medium text-foreground">Acceptable use</h2>
            <p className="mt-1">
              You may only scan MCP servers and repositories you own or have permission to scan. You
              may not use the service to attack, disrupt, or gain unauthorized access to systems you
              don&apos;t control. You may not attempt to circumvent usage limits through multiple
              accounts, automated signup, or similar abuse.
            </p>
          </section>
          <section>
            <h2 className="font-medium text-foreground">Billing</h2>
            <p className="mt-1">
              Paid plans are billed through Razorpay. You can cancel at any time from your account
              settings; you retain access through the end of the period you&apos;ve already paid for.
            </p>
          </section>
          <section>
            <h2 className="font-medium text-foreground">No warranty</h2>
            <p className="mt-1">
              Aevrin is a security scanning aid, not a guarantee. A clean scan does not mean an MCP
              server is safe to use — it means the specific checks we ran didn&apos;t find a problem.
              The service is provided as-is, without warranty of any kind.
            </p>
          </section>
          <section>
            <h2 className="font-medium text-foreground">Changes</h2>
            <p className="mt-1">
              We may update these terms as the product changes. Material changes will be reflected
              here with an updated date.
            </p>
          </section>
        </div>
      </div>
      <SiteFooter />
    </div>
  );
}
