import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { SiteFooter } from "@/widgets/site-footer";
import { Hero } from "./hero";
import { ProductFacts } from "./product-facts";
import { Capabilities } from "./capabilities";
import { RiskSection } from "./risk-section";

/**
 * The landing page.
 *
 * Design language is taken from the reference site rather than invented: a
 * display serif at light weight with -0.03em tracking, a grotesque body at
 * weight 500 with the same tracking, warm off-white paper against near-black
 * ink, square buttons for real actions and full pills reserved for chips.
 * Those tokens live in the `.marketing` block in `globals.css`, scoped so the
 * signed-in app is untouched, and defined for both themes so the header's
 * theme toggle keeps working here.
 *
 * Sections are ports of the ui-layouts and tailark block sets, rewritten
 * around this product's own data. Nothing on this page describes a capability
 * that does not exist.
 *
 * `primaryHref`/`signedIn` are fixed rather than read from a signed-in
 * cookie: this app is a static export with no server, and the authenticated
 * app lives on a different origin (`app.mcp.aevrin.net`), so there is no
 * same-origin session state to read here even client-side. A signed-in
 * visitor who lands on the marketing site sees "Start scanning free" and
 * goes through `/login` like anyone else, which redirects them straight
 * through since they already have a session - one extra hop, not a dead
 * end. See DECISIONS.md ADR-011.
 *
 * The full pricing comparison (`PricingSection`, with its Razorpay checkout
 * and live billing-plan fetch) stays on `/pricing` in the authenticated app
 * rather than being duplicated here - it's real integration weight this
 * static export doesn't need to carry for a teaser link.
 */

const PRIMARY_HREF = "https://app.mcp.aevrin.net/login";
const PRICING_HREF = "https://app.mcp.aevrin.net/pricing";

export function LandingPage() {
  return (
    <div className="marketing">
      <Hero primaryHref={PRIMARY_HREF} signedIn={false} />

      <RiskSection />

      <ProductFacts />

      <Capabilities />

      {/* Closing action, on the inverted ground the reference uses for its
          final band. */}
      <section
        className="px-6 py-24 lg:py-32"
        style={{ background: "var(--mk-invert-bg)", color: "var(--mk-invert-fg)" }}
      >
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="mk-h2">Scan the next one before you install it.</h2>
          <p className="mk-lede mx-auto mt-5" style={{ color: "var(--mk-invert-muted)" }}>
            Five CLI scans a month on the free plan, no card, nothing that renews on its own.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link
              href={PRIMARY_HREF}
              className="mk-btn"
              style={{ background: "var(--mk-invert-fg)", color: "var(--mk-invert-bg)" }}
            >
              Start scanning free
              <ArrowRight className="size-4" />
            </Link>
            <Link
              href={PRICING_HREF}
              className="mk-btn"
              style={{ border: "1px solid var(--mk-invert-line)", color: "var(--mk-invert-fg)" }}
            >
              See pricing
            </Link>
          </div>
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}
