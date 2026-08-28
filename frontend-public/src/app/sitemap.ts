import type { MetadataRoute } from "next";
import { execFileSync } from "node:child_process";
import path from "node:path";

// Static export needs this declared explicitly, the same way robots.ts and
// the marketing pages under app/ do (see DECISIONS.md ADR-011): metadata
// route files are dynamic by default and refuse to build under
// `output: "export"` without it.
export const revalidate = false;

const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "https://mcp.aevrin.net").replace(/\/$/, "");

/**
 * Real last-edit date from git history, not the filesystem mtime -- see the
 * identical function in `frontend/src/app/sitemap.ts` for the full
 * reasoning. Requires the CI checkout to use `fetch-depth: 0`.
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

// Every route this app actually serves. `/pricing` is deliberately absent:
// it stays on the authenticated app (see DECISIONS.md ADR-011) and is that
// app's sitemap entry to carry, not this one's.
const STATIC_ROUTES = [
  "src/app/page.tsx",
  "src/app/cli/page.tsx",
  "src/app/status/page.tsx",
  "src/app/terms/page.tsx",
  "src/app/privacy/page.tsx",
  "src/app/refund/page.tsx",
  "src/app/contact/page.tsx",
] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  return STATIC_ROUTES.map((file) => {
    const routePath = file
      .replace(/^src\/app/, "")
      .replace(/\/page\.tsx$/, "")
      .replace(/^$/, "/");
    return {
      url: `${SITE_URL}${routePath}`,
      lastModified: lastCommitDate(path.join(process.cwd(), file)),
    };
  });
}
