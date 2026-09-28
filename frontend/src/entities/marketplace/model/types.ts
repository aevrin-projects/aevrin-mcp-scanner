import type { Severity } from "@/entities/finding";

/**
 * Marketplace domain types.
 *
 * `security` and `popularity` are separate objects rather than flattened
 * fields, mirroring the API. That shape is deliberate and worth preserving:
 * it makes it awkward to write a component that treats a star count as a
 * safety signal, because the two never sit in the same object.
 */

export type TrustGrade = "A" | "B" | "C" | "D" | "F";

/**
 * How much the stored grade can be trusted to describe what someone is about
 * to install.
 *
 * - `complete`:       scanned, fully covered, and the scanned version is current.
 * - `partial`:        scanned, but a scanner stage did not run. Absence of
 *                      findings in those categories proves nothing.
 * - `outdated`:       the scan covers an older version than the current release.
 * - `ungraded`:       scanned, but the scan could not establish enough to
 *                      grade (a server that needs a credential to start, say).
 *                      Unknown, never safe.
 * - `unscanned`:      no evidence at all. Never render this as safe.
 * - `not_applicable`: not an MCP server: a prompt, a skill, a template. No
 *                      scanner exists for these; say so plainly.
 */
export type ScanState =
  | "complete"
  | "partial"
  | "outdated"
  | "ungraded"
  | "unscanned"
  | "not_applicable";

/**
 * What a registry item is. Mirrors ITEM_TYPES in
 * backend/api/aevrin_api/services/marketplace/items.py and the check in
 * migration 0048. Only `mcp_server` has a security scanner.
 */
export type ItemType =
  | "mcp_server"
  | "skill"
  | "prompt"
  | "tool"
  | "agent"
  | "component"
  | "template"
  | "workflow"
  | "library"
  | "cli"
  | "backend"
  | "frontend"
  | "infrastructure"
  | "product"
  | "repository"
  | "integration"
  | "dataset"
  | "documentation"
  | "other";

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
  | "az"
  | "trending";

export type InstallTarget = "claude-code" | "codex" | "cursor" | "generic";

export type PolicyAction = "allow" | "require_approval" | "block";

export interface ListingSecurity {
  grade: TrustGrade | null;
  /** 0-100, higher is worse. */
  risk_score: number | null;
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
 * Every field is nullable, and null means "not available", never zero.
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
  itemType: ItemType;
  author: string | null;
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
  technologies: string[];
  capabilities: string[];
  useCases: string[];
  repositoryRef: string | null;
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
  /** Whether the signed-in caller has saved this listing. Always `false`
   *  for a signed-out request -- there is no relationship to report. */
  favorited: boolean;
}

export interface ListingVersion {
  id: string;
  version: string;
  trustGrade: TrustGrade | null;
  /** 0-100, higher is worse. The code/MCP/dependency sub-scores that used to
   *  sit beside this are gone with the code-security product they described;
   *  the finding list, where each finding carries a rule id and its own
   *  evidence, answers "what earned this grade" better than they did. */
  riskScore: number | null;
  coverageComplete: boolean | null;
  scanId: string | null;
  scannedAt: string | null;
  firstSeenAt: string;
}

/**
 * The findings behind a published letter, ranked worst first.
 *
 * The grade and the risk score are claims; this is the evidence for them. It
 * is derived on read from the same scan the letter came from, so it can
 * neither disagree with the report nor go stale when a finding is triaged.
 */
export interface GradeDriver {
  ruleId: string;
  label: string;
  severity: Severity;
  /** How many tools this rule fired on. */
  occurrences: number;
}

export interface GradeRationale {
  scanId: string;
  version: string | null;
  severityCounts: Record<Severity, number>;
  drivers: GradeDriver[];
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

/**
 * What a registry item delivers, written by an Aevrin administrator. Keys are
 * present only when set; which ones matter depends on the item type (a prompt
 * has `prompt`, a skill has `instructions`).
 */
export interface ItemContent {
  prompt?: string;
  instructions?: string;
  usage?: string;
  documentation?: string;
  examples?: { title?: string; body: string }[];
  inputs?: string[];
  outputs?: string[];
  dependencies?: string[];
  compatibility?: string[];
}

export interface RelatedItem {
  id: string;
  slug: string;
  title: string;
  description: string;
  itemType: ItemType;
  grade: TrustGrade | null;
  /** `uses`: this item depends on it. `related`: see also. */
  relation: "uses" | "related";
}

/** A ready-to-copy client config per agent, secrets left blank. */
export type InstallConfigs = Partial<
  Record<InstallTarget, { config: Record<string, unknown>; warnings: string[] }>
>;

export interface ListingDetail extends Listing {
  readme: string | null;
  content: ItemContent;
  related: RelatedItem[];
  installConfigs: InstallConfigs;
  installation: {
    packages?: InstallPackage[];
    remotes?: { type: string; url: string | null }[];
  };
  versions: ListingVersion[];
  events: ListingEvent[];
  /** Null when the graded version has no scan, or that scan has no findings. */
  gradeRationale: GradeRationale | null;
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

export interface TypeCount {
  type: ItemType;
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
  F: "Do not use",
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
  // Named for what it measures. "Trending" alone would imply a signal the
  // registry does not have; this is views, among items updated recently.
  trending: "Most viewed this month",
};

/** Singular and plural labels per type, for badges, tabs and headings. */
export const ITEM_TYPE_LABELS: Record<ItemType, { one: string; many: string }> = {
  mcp_server: { one: "MCP server", many: "MCP servers" },
  skill: { one: "Skill", many: "Skills" },
  prompt: { one: "Prompt", many: "Prompts" },
  tool: { one: "Tool", many: "Tools" },
  agent: { one: "Agent", many: "Agents" },
  component: { one: "Component", many: "Components" },
  template: { one: "Template", many: "Templates" },
  workflow: { one: "Workflow", many: "Workflows" },
  library: { one: "Library", many: "Libraries" },
  cli: { one: "CLI", many: "CLIs" },
  backend: { one: "Backend", many: "Backend" },
  frontend: { one: "Frontend", many: "Frontend" },
  infrastructure: { one: "Infrastructure", many: "Infrastructure" },
  product: { one: "Product", many: "Products" },
  repository: { one: "Repository", many: "Repositories" },
  integration: { one: "Integration", many: "Integrations" },
  dataset: { one: "Dataset", many: "Datasets" },
  documentation: { one: "Documentation", many: "Documentation" },
  other: { one: "Other", many: "Other" },
};

/** Every type, in the order tabs and pickers show them. */
export const ITEM_TYPES = Object.keys(ITEM_TYPE_LABELS) as ItemType[];
