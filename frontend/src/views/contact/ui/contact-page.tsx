import Link from "next/link";
import { SiteFooter } from "@/widgets/site-footer";

/**
 * Payment providers check for a reachable contact page during merchant
 * review, and a mailto buried in the terms does not satisfy that. It is
 * also the page a customer looks for when a payment has gone wrong, so the
 * billing address is listed first and separately from general support.
 */
export function ContactPage() {
  return (
    <div>
      <div className="mx-auto max-w-2xl px-6 py-16">
        <h1 className="text-2xl font-semibold tracking-tight">Contact</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          We reply to everything within 3 business days.
        </p>

        <div className="mt-8 flex flex-col gap-6 text-sm leading-relaxed text-muted-foreground">
          <section>
            <h2 className="font-medium text-foreground">Billing and payments</h2>
            <p className="mt-1">
              <a href="mailto:support@aevrin.net" className="underline underline-offset-2">
                support@aevrin.net
              </a>
            </p>
            <p className="mt-2">
              For a charge you do not recognise, a payment that did not activate, or a refund
              request, include the payment date and amount and write from the address on the
              account. See the{" "}
              <Link href="/refund" className="underline underline-offset-2">
                Refund and Cancellation Policy
              </Link>{" "}
              for what is covered.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">Product support</h2>
            <p className="mt-1">
              <a href="mailto:support@aevrin.net" className="underline underline-offset-2">
                support@aevrin.net
              </a>
            </p>
            <p className="mt-2">
              For scan failures, include the scan ID from the dashboard URL. It tells us which
              scanners ran and which did not, which is usually the whole answer.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">Security reports</h2>
            <p className="mt-1">
              <a href="mailto:security@aevrin.net" className="underline underline-offset-2">
                security@aevrin.net
              </a>
            </p>
            <p className="mt-2">
              If you have found a vulnerability in Aevrin itself, please report it here rather than
              publicly, and give us a reasonable window to fix it before disclosing. We will not
              pursue action against good-faith research.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">Business details</h2>
            <p className="mt-1">
              Aevrin is operated from India and sells software services online. Service is
              delivered digitally through{" "}
              <Link href="/" className="underline underline-offset-2">
                mcp.aevrin.net
              </Link>{" "}
              and the Aevrin CLI. Nothing is physically shipped, so no shipping or delivery
              timelines apply.
            </p>
          </section>
        </div>
      </div>
      <SiteFooter />
    </div>
  );
}
