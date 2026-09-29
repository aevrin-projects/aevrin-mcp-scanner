import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Reveal } from "@/shared/ui/reveal";
import { SiteFooter } from "@/widgets/site-footer";
import { Faq } from "./faq";
import { Features } from "./features";
import { Hero } from "./hero";
import { Pricing } from "./pricing";
import { RiskSection } from "./risk-section";
import { SolutionBlocks } from "./solutions";
import { WorksWith } from "./works-with";

/**
 * The landing page: Aevrin's content and hero, in Folio's visual language
 * (serif statements, Geist for everything else, grey-scale chrome, hairlines,
 * 6px controls, a floating nav and footer), with the feature bento and the
 * pricing cards structured like the Nguyen reference. Tokens and type classes
 * are the `.marketing` block in globals.css. Nothing on this page describes a
 * capability that does not exist; each section cites its sources.
 *
 * `primaryHref`/`signedIn` are fixed rather than read from a cookie: this app
 * is a static export on a different origin from the authenticated app
 * (`app.mcp.aevrin.net`), so there is no session to read here. A signed-in
 * visitor goes through `/login`, which passes them straight through.
 * See DECISIONS.md ADR-011.
 */

const PRIMARY_HREF = "https://app.mcp.aevrin.net/login";

function FinalCta() {
  return (
    <section aria-labelledby="final-cta-title" className="relative overflow-hidden pt-16 pb-16 md:pt-28 md:pb-24">
      <div
        aria-hidden="true"
        className="mk-dots pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_50%_60%_at_50%_45%,black,transparent)]"
      />
      <Reveal className="mk-container relative text-center">
        <h2 id="final-cta-title" className="mk-h2-xl mx-auto max-w-4xl">
          Scan the next one before you install it.
        </h2>
        <p className="mk-lede mx-auto mt-6 max-w-xl">
          Five CLI scans a month on the free plan. No card, and nothing renews on its own.
        </p>
        <Link href={PRIMARY_HREF} className="mk-btn mk-btn-solid mk-btn-pill mt-9">
          Start scanning free
          <ArrowRight className="size-4" aria-hidden="true" />
        </Link>
      </Reveal>
    </section>
  );
}

export function LandingPage() {
  return (
    <>
      <Hero primaryHref={PRIMARY_HREF} signedIn={false} />
      <WorksWith />
      <RiskSection />
      <Features />
      <SolutionBlocks />
      <Pricing />
      <Faq />
      <FinalCta />
      <SiteFooter />
    </>
  );
}
