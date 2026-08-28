import Link from "next/link";
import { SiteFooter } from "@/widgets/site-footer";

/**
 * A standalone page rather than a section inside /terms, because payment
 * providers require a distinct, directly linkable refund policy and check
 * for one during merchant review.
 *
 * The policy is deliberately strict, but the three carve-outs below are not
 * discretionary: a duplicate charge, a charge for access never delivered,
 * and rights under India's Consumer Protection Act cannot be contracted
 * away, and a policy claiming otherwise is weaker in a dispute rather than
 * stronger.
 */
export function RefundPage() {
  return (
    <div>
      <div className="mx-auto max-w-2xl px-6 py-16">
        <h1 className="text-2xl font-semibold tracking-tight">Refund and Cancellation Policy</h1>
        <p className="mt-2 text-sm text-muted-foreground">Last updated: August 9, 2026.</p>

        <div className="mt-8 flex flex-col gap-6 text-sm leading-relaxed text-muted-foreground">
          <section>
            <h2 className="font-medium text-foreground">Summary</h2>
            <p className="mt-1">
              Aevrin paid plans are non-refundable. Each payment buys one billing cycle of access,
              which begins immediately. There is nothing to cancel: plans never renew
              automatically, so no further charge follows unless you choose to buy another cycle.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">Why access starts immediately</h2>
            <p className="mt-1">
              Paid access is granted the moment a payment is verified, and scanning capacity is
              available from that moment. Because the service is delivered in full at the start of
              the cycle rather than over time, payments are not refundable once access has been
              granted.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">Cancellation</h2>
            <p className="mt-1">
              There is no subscription to cancel. Aevrin does not store your card and does not
              charge you again. Paid access simply ends on the displayed paid-until date, after
              which the account returns to the Free plan and keeps working at Free limits. Stopping
              is a matter of not buying another cycle.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">When we do refund</h2>
            <p className="mt-1">
              Three situations are refunded regardless of the above, and you do not need to argue
              for them:
            </p>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              <li>
                <strong className="text-foreground">Duplicate charges.</strong> If the same cycle
                was paid for more than once, the extra payments are refunded in full.
              </li>
              <li>
                <strong className="text-foreground">Access never delivered.</strong> If a payment
                succeeded but the corresponding paid access was never applied to your account, and
                we cannot apply it, the payment is refunded in full.
              </li>
              <li>
                <strong className="text-foreground">Where the law requires it.</strong> Nothing
                here limits your rights under India&apos;s Consumer Protection Act, 2019 and its
                e-commerce rules, or under any other law that applies to you.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="font-medium text-foreground">What is not refundable</h2>
            <p className="mt-1">
              Unused scan quota, a change of mind, buying the wrong plan or billing cycle, and
              dissatisfaction with scan findings are not refundable. Scan results depend on the
              tools that ran and the code that was scanned; a scan that completes and reports
              nothing is a delivered result, not a failure to deliver.
            </p>
            <p className="mt-2">
              The Free plan exists so that the product can be evaluated before any payment. We
              recommend using it first.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">How to request a refund</h2>
            <p className="mt-1">
              Email{" "}
              <a href="mailto:support@aevrin.net" className="underline underline-offset-2">
                support@aevrin.net
              </a>{" "}
              from the address on the account, with the payment date and amount. We respond within
              3 business days. Approved refunds are issued to the original payment method through
              Razorpay and typically reach it within 5 to 7 business days, depending on your bank.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">Failed or incomplete payments</h2>
            <p className="mt-1">
              If a payment is debited but no paid access appears, do not pay again. Email us with
              the payment reference and we will either apply the access or refund the payment.
              Money debited on a genuinely failed payment is reversed by your bank without any
              action from us, usually within 5 to 7 business days.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">Related</h2>
            <p className="mt-1">
              See also our{" "}
              <Link href="/terms" className="underline underline-offset-2">
                Terms of Service
              </Link>{" "}
              and{" "}
              <Link href="/privacy" className="underline underline-offset-2">
                Privacy Policy
              </Link>
              . Pricing for every plan is listed on the{" "}
              <Link href="https://app.mcp.aevrin.net/pricing" className="underline underline-offset-2">
                pricing page
              </Link>
              .
            </p>
          </section>
        </div>
      </div>
      <SiteFooter />
    </div>
  );
}
