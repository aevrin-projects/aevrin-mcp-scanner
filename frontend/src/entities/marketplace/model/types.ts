/**
 * Registry domain types.
 *
 * The registry is discovery only: nothing here carries a scan result or a
 * grade. `popularity` is its own object, named for what each metric measures.
 * To security-check an MCP server, a user scans it on the scan page, which
 * runs the canonical scanner (`entities/scan`).
 */

/**
 * What a registry item is. Mirrors ITEM_TYPES in
 * backend/api/aevrin_api/services/marketplace/items.py and the check in
 * migration 0048.
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
  | "popular"
  | "recently_updated"
  | "recently_added"
  | "az"
  | "trending";

export type InstallTarget = "claude-code" | "codex" | "cursor" | "generic";

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
  popularity: ListingPopularity;
  status: string;
  visibility: "public" | "private" | "unlisted";
  createdAt: string | null;
  updatedAt: string | null;
  /** Whether the signed-in caller has saved this listing. Always `false`
   *  for a signed-out request -- there is no relationship to report. */
  favorited: boolean;
}

/** A version the registry has seen. A bare record: no scan state. */
export interface ListingVersion {
  id: string;
  version: string;
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
