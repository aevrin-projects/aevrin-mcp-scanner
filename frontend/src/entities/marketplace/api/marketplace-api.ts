"use client";

import { optionalAuthRequest, publicRequest, request } from "@/shared/api";
import type {
  Category,
  InstallConfigs,
  InstallTarget,
  ItemContent,
  ItemType,
  Listing,
  ListingDetail,
  ListingPage,
  MarketplaceSort,
  Submission,
  TypeCount,
} from "../model/types";

/**
 * Marketplace transport.
 *
 * Browse and detail go through `optionalAuthRequest`: the catalogue is public,
 * and a signed-out visitor must be able to browse it - but both responses carry
 * `is_favorited`, which is the caller's own relationship to a listing rather
 * than a property of it. They used `publicRequest`, which never sends
 * credentials, so that field came back false for everyone: saving a listing
 * worked and then appeared not to, because the read that would have shown it
 * was anonymous. Everything that writes, or that could surface an
 * organisation's private servers, uses `request`.
 *
 * The mapping functions exist because the API speaks snake_case and the app
 * speaks camelCase. They are explicit rather than a generic converter so that
 * a field the API stops sending becomes a visible `undefined` here rather
 * than silently vanishing from a panel.
 */

interface RawPopularity {
  github_stars: number | null;
  github_forks: number | null;
  github_open_issues: number | null;
  npm_downloads_last_month: number | null;
  favorites: number;
}

type RawListing = Record<string, unknown> & {
  popularity: RawPopularity;
};

function toListing(raw: RawListing): Listing {
  const popularity = raw.popularity;
  return {
    id: String(raw.id),
    slug: String(raw.slug),
    title: String(raw.title ?? ""),
    description: String(raw.description ?? ""),
    // Rows written before migration 0048 have no type; they were all servers.
    itemType: (raw.item_type as ItemType) ?? "mcp_server",
    author: (raw.author as string) ?? null,
    publisher: (raw.publisher as string) ?? null,
    repositoryUrl: (raw.repository_url as string) ?? null,
    homepageUrl: (raw.homepage_url as string) ?? null,
    registryUrl: (raw.registry_url as string) ?? null,
    registryName: (raw.registry_name as string) ?? null,
    source: (raw.source as Listing["source"]) ?? "registry",
    license: (raw.license as string) ?? null,
    categories: (raw.categories as string[]) ?? [],
    tags: (raw.tags as string[]) ?? [],
    technologies: (raw.technologies as string[]) ?? [],
    capabilities: (raw.capabilities as string[]) ?? [],
    useCases: (raw.use_cases as string[]) ?? [],
    repositoryRef: (raw.repository_ref as string) ?? null,
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
    favorited: Boolean(raw.is_favorited),
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
  type?: ItemType;
  technology?: string;
  category?: string;
  tag?: string;
  priceType?: string;
  installTarget?: string;
  sort?: MarketplaceSort;
  page?: number;
  pageSize?: number;
  featured?: boolean;
}

function toQuery(params: BrowseParams): string {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.type) search.set("type", params.type);
  if (params.technology) search.set("technology", params.technology);
  if (params.category) search.set("category", params.category);
  if (params.tag) search.set("tag", params.tag);
  if (params.priceType) search.set("price_type", params.priceType);
  if (params.installTarget) search.set("install_target", params.installTarget);
  if (params.sort) search.set("sort", params.sort);
  if (params.page && params.page > 1) search.set("page", String(params.page));
  if (params.pageSize) search.set("page_size", String(params.pageSize));
  if (params.featured) search.set("featured", "true");
  const query = search.toString();
  return query ? `?${query}` : "";
}

export async function browseListings(params: BrowseParams = {}): Promise<ListingPage> {
  // optionalAuth, not public: the response carries `is_favorited`, which is
  // the caller's own relationship to each listing and is silently false for
  // an anonymous read.
  const raw = await optionalAuthRequest<{
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
  // optionalAuth for the same reason as browseListings: readable signed out,
  // but `is_favorited` needs to know who is asking.
  const raw = await optionalAuthRequest<RawListing>(
    `/marketplace/mcp/${encodeURIComponent(slug)}`,
  );
  return toListingDetail(raw);
}

/**
 * The detail mapping, exported so the admin editor's preview maps its payload
 * with exactly this function. Two mappers would let the preview show something
 * the public page does not.
 */
export function toListingDetail(raw: Record<string, unknown>): ListingDetail {
  const base = toListing(raw as RawListing);
  return {
    ...base,
    readme: (raw.readme as string) ?? null,
    content: (raw.content as ItemContent) ?? {},
    installConfigs: (raw.install_configs as InstallConfigs) ?? {},
    related: ((raw.related as Record<string, unknown>[]) ?? []).map((r) => ({
      id: String(r.id),
      slug: String(r.slug),
      title: String(r.title ?? r.slug),
      description: String(r.description ?? ""),
      itemType: (r.item_type as ItemType) ?? "mcp_server",
      relation: r.relation === "uses" ? "uses" : "related",
    })),
    installation: (raw.installation as ListingDetail["installation"]) ?? {},
    marketplaceViews: Number(raw.marketplace_views ?? 0),
    versions: ((raw.versions as Record<string, unknown>[]) ?? []).map((v) => ({
      id: String(v.id),
      version: String(v.version),
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

/** Published items per type. Types with none are omitted by the API. */
export async function listTypes(): Promise<TypeCount[]> {
  return publicRequest<TypeCount[]>("/marketplace/types");
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
