/**
 * Marketplace domain types.
 *
 * `security` and `popularity` are separate objects rather than flattened
 * fields, mirroring the API. That shape is deliberate and worth preserving:
 * it makes it awkward to write a component that treats a star count as a
 * safety signal, because the two never sit in the same object.
 */

export type TrustGrade = "A" | "B" | "C" | "D";

/**
 * How much the stored grade can be trusted to describe what someone is about
 * to install.
 *
 * - `complete`  — scanned, fully covered, and the scanned version is current.
 * - `partial`   — scanned, but a scanner stage did not run. Absence of
 *                 findings in those categories proves nothing.
 * - `outdated`  — the scan covers an older version than the current release.
 * - `unscanned` — no evidence at all. Never render this as safe.
 */
export type ScanState = "complete" | "partial" | "outdated" | "unscanned";

export type PriceType =
  | "free"
  | "freemium"
  | "paid"
  | "open_source"
  | "commercial"
  | "unknown";

export type MarketplaceSort =
  | "recommended"
  | "security"
  | "popular"
  | "recently_updated"
  | "recently_added"
  | "az";

export type InstallTarget = "claude-code" | "codex" | "cursor" | "generic";

export type PolicyAction = "allow" | "require_approval" | "block";

export interface ListingSecurity {
  grade: TrustGrade | null;
  score: number | null;
  /** The version the grade actually belongs to. */
  scannedVersion: string | null;
  latestVersion: string | null;
  coverageComplete: boolean | null;
  scannedAt: string | null;
  state: ScanState;
  /** False whenever the grade does not describe the current release. */
  appliesToLatest: boolean;
  label: string;
  badges: string[];
}

/**
 * Every field is nullable, and null means "not available" — never zero.
 * A repository whose metadata could not be fetched has unknown stars, and
 * rendering that as `0` would publish a false claim about someone's project.
 */
export interface ListingPopularity {
  githubStars: number | null;
  githubForks: number | null;
  githubOpenIssues: number | null;
  npmDownloadsLastMonth: number | null;
  favorites: number;
}

export interface Listing {
  id: string;
  slug: string;
  title: string;
  description: string;
  publisher: string | null;
  repositoryUrl: string | null;
  homepageUrl: string | null;
  registryUrl: string | null;
  registryName: string | null;
  /** Where this listing came from. Shown, never hidden. */
  source: "registry" | "admin" | "user_submission";
  license: string | null;
  categories: string[];
  tags: string[];
  priceType: PriceType;
  pricingUrl: string | null;
  installTargets: InstallTarget[];
  featured: boolean;
  latestVersion: string | null;
  githubLanguage: string | null;
  githubLastCommitAt: string | null;
  githubLatestRelease: string | null;
  rankingScore: number;
  security: ListingSecurity;
  popularity: ListingPopularity;
  status: string;
  visibility: "public" | "private" | "unlisted";
  createdAt: string | null;
  updatedAt: string | null;
}

export interface ListingVersion {
  id: string;
  version: string;
  trustGrade: TrustGrade | null;
  securityScore: number | null;
  coverageComplete: boolean | null;
  codeScore: number | null;
  mcpScore: number | null;
  dependencyScore: number | null;
  scanId: string | null;
  scannedAt: string | null;
  firstSeenAt: string;
}

export interface ListingEvent {
  id: string;
  eventType: string;
  oldValue: string | null;
  newValue: string | null;
  reason: string | null;
  severity: "info" | "warning" | "critical";
  createdAt: string;
}

export interface ListingDetail extends Listing {
  readme: string | null;
  installation: {
    packages?: InstallPackage[];
    remotes?: { type: string; url: string | null }[];
  };
  versions: ListingVersion[];
  events: ListingEvent[];
  marketplaceViews: number;
}

export interface InstallPackage {
  registry_type: string;
  identifier: string;
  version: string;
  runtime_hint: string;
  transport: string;
  file_sha256: string | null;
  environment: {
    name: string;
    required: boolean;
    secret: boolean;
    description: string;
  }[];
}

export interface ListingPage {
  items: Listing[];
  page: number;
  pageSize: number;
  hasMore: boolean;
  sort: MarketplaceSort;
}

export interface Category {
  slug: string;
  name: string;
  description: string | null;
  count: number;
}

export interface InstallPlan {
  listing: Listing;
  agent: InstallTarget;
  scope: "global" | "project";
  config: Record<string, unknown>;
  capabilities: string[];
  warnings: string[];
  policyAction: PolicyAction;
  policyReason: string | null;
}

export interface Submission {
  id: string;
  sourceUrl: string;
  note: string | null;
  status: string;
  reviewReason: string | null;
  createdAt: string;
  listing: Pick<
    Listing,
    "id" | "slug" | "title" | "status" | "repositoryUrl"
  > | null;
}

export interface OrgPolicy {
  gradeActions: Record<TrustGrade, PolicyAction>;
  unscannedAction: PolicyAction;
}

/** Human labels for a grade. Kept beside the type so every surface agrees. */
export const GRADE_LABELS: Record<TrustGrade, string> = {
  A: "Trusted",
  B: "Generally safe",
  C: "Caution",
  D: "High risk",
};

export const PRICE_LABELS: Record<PriceType, string> = {
  free: "Free",
  freemium: "Freemium",
  paid: "Paid",
  open_source: "Open source",
  commercial: "Commercial",
  // Never "Free". An unknown price shown as free is the single most damaging
  // inaccuracy this catalogue could publish, because "free and open" is
  // exactly the phrase that makes someone skip their own diligence.
  unknown: "Not stated",
};

export const INSTALL_TARGET_LABELS: Record<InstallTarget, string> = {
  "claude-code": "Claude Code",
  codex: "Codex",
  cursor: "Cursor",
  generic: "Generic MCP",
};

export const SORT_LABELS: Record<MarketplaceSort, string> = {
  recommended: "Recommended",
  security: "Security",
  popular: "Popular",
  recently_updated: "Recently updated",
  recently_added: "Recently added",
  az: "A–Z",
};
