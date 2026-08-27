import Link from "next/link";
import { headers } from "next/headers";
import { ArrowRight } from "lucide-react";
import { PricingSection } from "@/widgets/pricing";
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
 */

export async function LandingPage() {
  const headersList = await headers();
  const signedIn = Boolean(headersList.get("x-aevrin-user-email"));
  const primaryHref = signedIn ? "/dashboard" : "/login";

  return (
    <div className="marketing">
      <Hero primaryHref={primaryHref} signedIn={signedIn} />

      <RiskSection />

      <ProductFacts />

      <Capabilities />

      <PricingSection />

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
              href={primaryHref}
              className="mk-btn"
              style={{ background: "var(--mk-invert-fg)", color: "var(--mk-invert-bg)" }}
            >
              {signedIn ? "Open dashboard" : "Start scanning free"}
              <ArrowRight className="size-4" />
            </Link>
            <Link
              href="/docs"
              className="mk-btn"
              style={{ border: "1px solid var(--mk-invert-line)", color: "var(--mk-invert-fg)" }}
            >
              Read the docs
            </Link>
          </div>
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}
