import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";

export const metadata: Metadata = {
  title: "Privacy Policy — Aevrin",
  description: "How Aevrin handles account, scan, abuse-prevention, and billing data.",
};

export default function PrivacyPage() {
  return (
    <div>
      <div className="mx-auto max-w-2xl px-6 py-16">
        <h1 className="text-2xl font-semibold tracking-tight">Privacy Policy</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Last updated: August 3, 2026.
        </p>

        <div className="mt-8 flex flex-col gap-6 text-sm leading-relaxed text-muted-foreground">
          <section>
            <h2 className="font-medium text-foreground">What we collect</h2>
            <ul className="mt-2 list-disc pl-5">
              <li>Account info: your email address, and if you sign in with Google, the basic profile info Google shares.</li>
              <li>Scan data: the repository URLs, server URLs, or config you submit for scanning, and the findings we generate from them.</li>
              <li>
                Abuse-prevention signals: a browser fingerprint (via the open-source FingerprintJS
                library) when you approve a device login, a hashed machine identifier from the CLI
                and Claude Code hook, and your IP address — used only to detect unusual
                multi-account signup patterns, never sold or used for advertising.
              </li>
              <li>Billing info: handled directly by Razorpay — we store your subscription status, not your card details.</li>
            </ul>
          </section>
          <section>
            <h2 className="font-medium text-foreground">Why we collect it</h2>
            <p className="mt-1">
              To run the service (scanning, showing you results, metering usage against your plan),
              to prevent abuse of the free tier, and to bill paid plans. We don&apos;t use your data
              for anything beyond operating Aevrin.
            </p>
          </section>
          <section>
            <h2 className="font-medium text-foreground">What we don&apos;t do</h2>
            <p className="mt-1">
              We don&apos;t sell your data. We don&apos;t use scan targets or findings for anything
              other than showing them back to you. We don&apos;t share machine/fingerprint signals
              outside of Aevrin&apos;s own abuse-prevention checks.
            </p>
          </section>
          <section>
            <h2 className="font-medium text-foreground">Source handling</h2>
            <p className="mt-1">
              Repository contents are cloned into temporary scan-worker storage and are not kept
              as part of scan history. Pasted configuration is processed by the scan job; durable
              history stores a fingerprinted label rather than the submitted configuration text.
              Findings, target identifiers, stages, and report data are retained in your account.
            </p>
          </section>
          <section>
            <h2 className="font-medium text-foreground">Automated analysis</h2>
            <p className="mt-1">
              The current scan pipeline uses the security tools identified in the product
              methodology. It does not send repositories or findings to an external language model
              to decide whether a vulnerability exists.
            </p>
          </section>
          <section>
            <h2 className="font-medium text-foreground">Retention</h2>
            <p className="mt-1">
              Plan screens show the configured history window. You may delete an individual scan
              or clear your scan history at any time. Automated retention pruning is not currently
              presented as a guarantee.
            </p>
          </section>
          <section>
            <h2 className="font-medium text-foreground">Your data</h2>
            <p className="mt-1">
              You can revoke API keys and delete individual scans or all scan history from your
              account. Full account deletion is not currently self-service; this page will be
              updated with the operator&apos;s request channel before that flow is offered.
            </p>
          </section>
        </div>
      </div>
      <SiteFooter />
    </div>
  );
}
