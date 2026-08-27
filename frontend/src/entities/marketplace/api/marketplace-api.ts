"use client";

import { publicRequest, request } from "@/shared/api";
import type {
  Category,
  InstallPlan,
  InstallTarget,
  Listing,
  ListingDetail,
  ListingPage,
  MarketplaceSort,
  OrgPolicy,
  Submission,
} from "../model/types";

/**
 * Marketplace transport.
 *
 * Browse and detail go through `publicRequest`: the catalogue is public, and
 * a signed-out visitor must be able to read a security grade before deciding
 * whether Aevrin is worth signing up for. Everything that writes, or that
 * could surface an organisation's private servers, uses `request`.
 *
 * The mapping functions exist because the API speaks snake_case and the app
 * speaks camelCase. They are explicit rather than a generic converter so that
 * a field the API stops sending becomes a visible `undefined` here rather
 * than silently vanishing from a security panel.
 */

interface RawSecurity {
  grade: string | null;
  score: number | null;
  scanned_version: string | null;
  latest_version: string | null;
  coverage_complete: boolean | null;
  scanned_at: string | null;
  state: string;
  applies_to_latest: boolean;
  label: string;
  badges: string[];
}

interface RawPopularity {
  github_stars: number | null;
  github_forks: number | null;
  github_open_issues: number | null;
  npm_downloads_last_month: number | null;
  favorites: number;
}

type RawListing = Record<string, unknown> & {
  security: RawSecurity;
  popularity: RawPopularity;
};

function toListing(raw: RawListing): Listing {
  const security = raw.security;
  const popularity = raw.popularity;
  return {
    id: String(raw.id),
    slug: String(raw.slug),
    title: String(raw.title ?? ""),
    description: String(raw.description ?? ""),
    publisher: (raw.publisher as string) ?? null,
    repositoryUrl: (raw.repository_url as string) ?? null,
    homepageUrl: (raw.homepage_url as string) ?? null,
    registryUrl: (raw.registry_url as string) ?? null,
    registryName: (raw.registry_name as string) ?? null,
    source: (raw.source as Listing["source"]) ?? "registry",
    license: (raw.license as string) ?? null,
    categories: (raw.categories as string[]) ?? [],
    tags: (raw.tags as string[]) ?? [],
    priceType: (raw.price_type as Listing["priceType"]) ?? "unknown",
    pricingUrl: (raw.pricing_url as string) ?? null,
    installTargets: (raw.install_targets as InstallTarget[]) ?? [],
    featured: Boolean(raw.featured),
    latestVersion: (raw.latest_version as string) ?? null,
    githubLanguage: (raw.github_language as string) ?? null,
    githubLastCommitAt: (raw.github_last_commit_at as string) ?? null,
    githubLatestRelease: (raw.github_latest_release as string) ?? null,
    rankingScore: Number(raw.ranking_score ?? 0),
    status: String(raw.status ?? "published"),
    visibility: (raw.visibility as Listing["visibility"]) ?? "public",
    createdAt: (raw.created_at as string) ?? null,
    updatedAt: (raw.updated_at as string) ?? null,
    security: {
      grade: (security?.grade as Listing["security"]["grade"]) ?? null,
      score: security?.score ?? null,
      scannedVersion: security?.scanned_version ?? null,
      latestVersion: security?.latest_version ?? null,
      coverageComplete: security?.coverage_complete ?? null,
      scannedAt: security?.scanned_at ?? null,
      state: (security?.state as Listing["security"]["state"]) ?? "unscanned",
      appliesToLatest: Boolean(security?.applies_to_latest),
      label: security?.label ?? "Not yet scanned",
      badges: security?.badges ?? [],
    },
    popularity: {
      // `?? null` rather than `?? 0` throughout, deliberately. An absent
      // metric must stay absent all the way to the component that decides
      // whether to render "—" or a number.
      githubStars: popularity?.github_stars ?? null,
      githubForks: popularity?.github_forks ?? null,
      githubOpenIssues: popularity?.github_open_issues ?? null,
      npmDownloadsLastMonth: popularity?.npm_downloads_last_month ?? null,
      favorites: popularity?.favorites ?? 0,
    },
  };
}

export interface BrowseParams {
  q?: string;
  category?: string;
  tag?: string;
  priceType?: string;
  installTarget?: string;
  minGrade?: string;
  sort?: MarketplaceSort;
  page?: number;
  pageSize?: number;
  featured?: boolean;
}

function toQuery(params: BrowseParams): string {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.category) search.set("category", params.category);
  if (params.tag) search.set("tag", params.tag);
  if (params.priceType) search.set("price_type", params.priceType);
  if (params.installTarget) search.set("install_target", params.installTarget);
  if (params.minGrade) search.set("min_grade", params.minGrade);
  if (params.sort) search.set("sort", params.sort);
  if (params.page && params.page > 1) search.set("page", String(params.page));
  if (params.pageSize) search.set("page_size", String(params.pageSize));
  if (params.featured) search.set("featured", "true");
  const query = search.toString();
  return query ? `?${query}` : "";
}

export async function browseListings(params: BrowseParams = {}): Promise<ListingPage> {
  const raw = await publicRequest<{
    items: RawListing[];
    page: number;
    page_size: number;
    has_more: boolean;
    sort: MarketplaceSort;
  }>(`/marketplace/mcp${toQuery(params)}`);
  return {
    items: raw.items.map(toListing),
    page: raw.page,
    pageSize: raw.page_size,
    hasMore: raw.has_more,
    sort: raw.sort,
  };
}

export async function getListing(slug: string): Promise<ListingDetail> {
  const raw = await publicRequest<RawListing>(`/marketplace/mcp/${encodeURIComponent(slug)}`);
  const base = toListing(raw);
  return {
    ...base,
    readme: (raw.readme as string) ?? null,
    installation: (raw.installation as ListingDetail["installation"]) ?? {},
    marketplaceViews: Number(raw.marketplace_views ?? 0),
    versions: ((raw.versions as Record<string, unknown>[]) ?? []).map((v) => ({
      id: String(v.id),
      version: String(v.version),
      trustGrade: (v.trust_grade as ListingDetail["security"]["grade"]) ?? null,
      securityScore: (v.security_score as number) ?? null,
      coverageComplete: (v.coverage_complete as boolean) ?? null,
      codeScore: (v.code_score as number) ?? null,
      mcpScore: (v.mcp_score as number) ?? null,
      dependencyScore: (v.dependency_score as number) ?? null,
      scanId: (v.scan_id as string) ?? null,
      scannedAt: (v.scanned_at as string) ?? null,
      firstSeenAt: String(v.first_seen_at ?? ""),
    })),
    events: ((raw.events as Record<string, unknown>[]) ?? []).map((e) => ({
      id: String(e.id),
      eventType: String(e.event_type),
      oldValue: (e.old_value as string) ?? null,
      newValue: (e.new_value as string) ?? null,
      reason: (e.reason as string) ?? null,
      severity: (e.severity as ListingDetail["events"][number]["severity"]) ?? "info",
      createdAt: String(e.created_at ?? ""),
    })),
  };
}

export async function listCategories(): Promise<Category[]> {
  return publicRequest<Category[]>("/marketplace/categories");
}

export async function getInstallPlan(
  slug: string,
  agent: InstallTarget,
  scope: "global" | "project",
): Promise<InstallPlan> {
  const raw = await request<Record<string, unknown>>(
    `/marketplace/mcp/${encodeURIComponent(slug)}/install-plan`,
    { method: "POST", body: JSON.stringify({ agent, scope }) },
  );
  return {
    listing: toListing(raw.listing as RawListing),
    agent: raw.agent as InstallTarget,
    scope: raw.scope as "global" | "project",
    config: (raw.config as Record<string, unknown>) ?? {},
    capabilities: (raw.capabilities as string[]) ?? [],
    warnings: (raw.warnings as string[]) ?? [],
    policyAction: (raw.policy_action as InstallPlan["policyAction"]) ?? "allow",
    policyReason: (raw.policy_reason as string) ?? null,
  };
}

export async function submitServer(sourceUrl: string, note?: string) {
  return request<{ submission: Record<string, unknown> }>("/marketplace/submissions", {
    method: "POST",
    body: JSON.stringify({ source_url: sourceUrl, note: note || null }),
  });
}

export async function listMySubmissions(): Promise<Submission[]> {
  const raw = await request<Record<string, unknown>[]>("/marketplace/submissions");
  return raw.map((s) => {
    const listing = s.listing as Record<string, unknown> | null;
    return {
      id: String(s.id),
      sourceUrl: String(s.source_url),
      note: (s.note as string) ?? null,
      status: String(s.status),
      reviewReason: (s.review_reason as string) ?? null,
      createdAt: String(s.created_at ?? ""),
      listing: listing
        ? {
            id: String(listing.id),
            slug: String(listing.slug),
            title: String(listing.title),
            status: String(listing.status),
            repositoryUrl: (listing.repository_url as string) ?? null,
          }
        : null,
    };
  });
}

export async function reportListing(
  listingId: string,
  kind: "listing" | "security",
  reason: string,
  description?: string,
) {
  return request(`/marketplace/mcp/${listingId}/report`, {
    method: "POST",
    body: JSON.stringify({ kind, reason, description: description || null }),
  });
}

export async function setFavorite(listingId: string, favorite: boolean) {
  return request<{ favorite: boolean }>(`/marketplace/mcp/${listingId}/favorite`, {
    method: "PUT",
    body: JSON.stringify({ favorite }),
  });
}

export async function listFavorites(): Promise<Listing[]> {
  const raw = await request<RawListing[]>("/marketplace/favorites");
  return raw.map(toListing);
}

export async function getPolicy(): Promise<OrgPolicy> {
  const raw = await request<Record<string, unknown>>("/marketplace/policy");
  return {
    gradeActions: (raw.grade_actions as OrgPolicy["gradeActions"]) ?? {
      A: "allow",
      B: "allow",
      C: "require_approval",
      D: "block",
    },
    unscannedAction: (raw.unscanned_action as OrgPolicy["unscannedAction"]) ?? "require_approval",
  };
}

export async function setPolicy(policy: OrgPolicy): Promise<OrgPolicy> {
  const raw = await request<Record<string, unknown>>("/marketplace/policy", {
    method: "PUT",
    body: JSON.stringify({
      grade_actions: policy.gradeActions,
      unscanned_action: policy.unscannedAction,
    }),
  });
  return {
    gradeActions: raw.grade_actions as OrgPolicy["gradeActions"],
    unscannedAction: raw.unscanned_action as OrgPolicy["unscannedAction"],
  };
}
