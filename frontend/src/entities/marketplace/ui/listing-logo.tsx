import type { ComponentType } from "react";
import {
  FiBarChart2,
  FiBookOpen,
  FiBriefcase,
  FiCheckSquare,
  FiCloud,
  FiCode,
  FiCpu,
  FiDatabase,
  FiDollarSign,
  FiFolder,
  FiGlobe,
  FiGrid,
  FiMessageCircle,
  FiSearch,
  FiServer,
  FiShield,
  FiTrendingUp,
} from "react-icons/fi";

import { BRAND_NAMES, BrandIcon, type BrandName } from "@/shared/ui/brand-icon";
import type { Listing } from "../model/types";

/**
 * The one small mark that answers "what kind of thing is this" before a
 * reader has read the title -- the piece every browse card was missing.
 *
 * A real company mark when the listing's own tags name one (Slack, AWS,
 * Postgres...), never guessed: the tag vocabulary is the same one
 * `normalize.py` derives from the publisher's own text, so a mark only ever
 * appears when the publisher's own words support it. Otherwise, a generic
 * icon for the listing's first category. Every listing has at least one
 * category (`normalize.py` falls back to `"other"`), so this never renders
 * blank.
 */

const CATEGORY_ICONS: Record<string, ComponentType<{ className?: string }>> = {
  databases: FiDatabase,
  "developer-tools": FiCode,
  cloud: FiCloud,
  search: FiSearch,
  productivity: FiCheckSquare,
  communication: FiMessageCircle,
  business: FiBriefcase,
  finance: FiDollarSign,
  analytics: FiBarChart2,
  devops: FiServer,
  security: FiShield,
  "browser-web": FiGlobe,
  "files-storage": FiFolder,
  marketing: FiTrendingUp,
  "ai-ml": FiCpu,
  research: FiBookOpen,
  other: FiGrid,
};

function brandTag(tags: string[]): BrandName | null {
  const match = tags.find((tag) => BRAND_NAMES.has(tag as BrandName));
  return (match as BrandName) ?? null;
}

export function ListingLogo({
  listing,
  className = "size-9",
}: {
  listing: Pick<Listing, "tags" | "categories">;
  className?: string;
}) {
  const brand = brandTag(listing.tags);
  const category = listing.categories[0] ?? "other";
  const CategoryIcon = CATEGORY_ICONS[category] ?? FiGrid;

  return (
    <div
      className={`grid shrink-0 place-items-center rounded-lg border border-border bg-muted/40 ${className}`}
    >
      {brand ? (
        <BrandIcon name={brand} className="size-1/2" />
      ) : (
        <CategoryIcon className="size-1/2 text-muted-foreground" />
      )}
    </div>
  );
}
