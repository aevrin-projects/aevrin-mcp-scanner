import type { MetadataRoute } from "next";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { source } from "@/shared/lib/docs-source";

// Same fallback pattern as siteUrl() in auth/callback, auth/confirm, and
// login/actions.ts; this file can't import a shared helper because those
// live in "use server" modules, so the constant is duplicated deliberately
// rather than pulling server-action code into a route this trivial.
const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "https://mcp.aevrin.net").replace(/\/$/, "");

/**
 * Real last-edit date from git history, not the filesystem mtime. A CI
 * build re-copies every file from a fresh checkout, so `fs.statSync(...).mtime`
 * is always "now"; every URL would report a new lastmod on every single
 * deploy, which is exactly the fabricated-freshness signal Google's sitemap
 * guidance says to avoid. `undefined` (omitting lastModified) is valid per
 * the sitemap spec and is what this falls back to if git isn't available in
 * the build environment.
 */
function lastCommitDate(absoluteFilePath: string): Date | undefined {
  try {
    const iso = execFileSync("git", ["log", "-1", "--format=%cI", "--", absoluteFilePath], {
      cwd: process.cwd(),
      encoding: "utf8",
    }).trim();
    return iso ? new Date(iso) : undefined;
  } catch {
    return undefined;
  }
}

// Only the routes that are genuinely public, unique, and meant to rank:
// marketing pages and the docs. Everything under /dashboard, /scans,
// /settings, /integrations, /usage, /onboarding requires a signed-in
// session and redirects to /login for everyone else, indexing a login wall
// wastes crawl budget and Google explicitly downranks sites that submit
// pages behind auth. /login and /device are functional, not content: no
// unique copy to rank on. /error is never a real destination. /docs/llms.txt
// is a machine-readable feed, not an HTML page for search results.
const STATIC_ROUTES = [
  "src/app/page.tsx",
  "src/app/pricing/page.tsx",
  "src/app/cli/page.tsx",
  "src/app/status/page.tsx",
  "src/app/terms/page.tsx",
  "src/app/privacy/page.tsx",
  "src/app/refund/page.tsx",
  "src/app/contact/page.tsx",
] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  const staticEntries: MetadataRoute.Sitemap = STATIC_ROUTES.map((file) => {
    const routePath = file
      .replace(/^src\/app/, "")
      .replace(/\/page\.tsx$/, "")
      .replace(/^$/, "/");
    return {
      url: `${SITE_URL}${routePath}`,
      lastModified: lastCommitDate(path.join(process.cwd(), file)),
    };
  });

  // Every real docs page, driven by the same fumadocs source /docs itself
  // renders from, a new file dropped into content/ appears here with
  // no manual list to keep in sync, and a deleted or renamed page can't
  // leave a stale 404 URL behind.
  const docEntries: MetadataRoute.Sitemap = source.getPages().map((page) => ({
    url: `${SITE_URL}${page.url}`,
    lastModified: lastCommitDate(page.absolutePath ?? path.join(process.cwd(), "content", page.path)),
  }));

  return [...staticEntries, ...docEntries];
}
