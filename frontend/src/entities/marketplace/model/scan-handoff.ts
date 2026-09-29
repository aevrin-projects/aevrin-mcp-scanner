import type { ListingDetail } from "./types";

/**
 * How to scan a registry MCP server with Aevrin's own scanner.
 *
 * The registry does not scan. This only builds a link to the existing scan
 * page, prefilled through the `mode` and `target` query parameters it already
 * reads, or, for a server that exists only as a package, the canonical CLI
 * command. The checks mirror the scan page's own validation, so a link never
 * lands on a form that immediately refuses its target.
 */
export type ScanHandoff =
  | { kind: "link"; href: string }
  | { kind: "command"; command: string }
  | null;

// A package name or version that is safe to show inside a quoted command.
// Anything else gets no command rather than a command that means something
// other than what it appears to.
const PLAIN = /^[A-Za-z0-9@._/+-]+$/;
const RUNNERS: Record<string, string> = { npm: "npx -y", pypi: "uvx" };

function scanLink(mode: "github_repo" | "live_mcp_server", target: string) {
  return `/scans/new?mode=${mode}&target=${encodeURIComponent(target)}`;
}

function githubRepository(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    const segments = url.pathname.split("/").filter(Boolean);
    return url.protocol === "https:" && url.hostname === "github.com" && segments.length >= 2
      ? value
      : null;
  } catch {
    return null;
  }
}

function httpsUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    return new URL(value).protocol === "https:" ? value : null;
  } catch {
    return null;
  }
}

export function scanHandoff(
  listing: Pick<ListingDetail, "itemType" | "repositoryUrl" | "installation">,
): ScanHandoff {
  if (listing.itemType !== "mcp_server") return null;

  const repository = githubRepository(listing.repositoryUrl);
  if (repository) return { kind: "link", href: scanLink("github_repo", repository) };

  const remote = httpsUrl(listing.installation.remotes?.[0]?.url);
  if (remote) return { kind: "link", href: scanLink("live_mcp_server", remote) };

  const pkg = listing.installation.packages?.[0];
  const runner = pkg ? RUNNERS[pkg.registry_type] : undefined;
  if (!pkg || !runner || !PLAIN.test(pkg.identifier)) return null;
  const version = pkg.version && PLAIN.test(pkg.version) ? `@${pkg.version}` : "";
  return { kind: "command", command: `aevrin scan mcp "${runner} ${pkg.identifier}${version}"` };
}
