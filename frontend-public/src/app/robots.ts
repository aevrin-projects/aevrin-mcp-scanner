import type { MetadataRoute } from "next";

export const revalidate = false;

const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "https://mcp.aevrin.net").replace(/\/$/, "");

// This app serves only public marketing/content routes -- there is nothing
// auth-gated here to disallow (that list lives in the authenticated app's
// own robots.ts). See DECISIONS.md ADR-011.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
