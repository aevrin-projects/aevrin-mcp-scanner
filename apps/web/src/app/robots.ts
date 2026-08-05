import type { MetadataRoute } from "next";

const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "https://mcp.aevrin.net").replace(/\/$/, "");

/**
 * Disallow list mirrors PROTECTED_PATH_PREFIXES in lib/supabase/proxy.ts —
 * every route that requires a signed-in session and would otherwise send a
 * crawler straight to a /login redirect. Crawling those wastes budget on a
 * page with no unique content, and Google's own guidance is to keep
 * auth-gated routes out of discovery entirely rather than let it find them
 * and (correctly) decide not to index them. /api/* is data, not a page.
 * /device is the CLI pairing flow and never a real search destination.
 * /error only exists mid-redirect.
 *
 * Nothing here is `noindex` at the page level (see individual page
 * metadata) — this only stops crawling. A route could still get indexed
 * from an external link even if disallowed; that's what x-robots-tag /
 * <meta name="robots"> would be for, and none of these routes have inbound
 * links worth worrying about.
 *
 * No `host` field: that's a Yandex-only directive Google has never honored
 * (and, as of an April 2026 update to Google's own robotstxt repo, now
 * explicitly documents as unsupported alongside crawl-delay and
 * clean-param). The `sitemap` field below is the one line Google actually
 * reads from this file.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: [
        "/dashboard",
        "/scans",
        "/settings",
        "/integrations",
        "/usage",
        "/onboarding",
        "/api/",
        "/device",
        "/error",
      ],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
