"use client";

import { useState, type ComponentType } from "react";
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
 * reader has read the title.
 *
 * Three tiers, strongest evidence first:
 *
 * 1. **The publisher's own avatar**, from the GitHub owner in their declared
 *    `repository_url`. This is the project's real mark -- the one they chose
 *    for themselves -- and it identifies *this* server rather than a category
 *    it happens to fall into.
 * 2. **A company mark** (`thesvg`) when the listing's tags name one. Weaker
 *    than the avatar on purpose: tags come from keyword matching over the
 *    publisher's prose (`normalize.py`), so a server that merely *mentions*
 *    Slack can carry a `slack` tag without being Slack's. Showing someone
 *    else's brand on an unrelated project is a false provenance claim, so it
 *    never outranks the publisher's own avatar.
 * 3. **A generic category icon** (`react-icons`), which always resolves --
 *    `normalize.py` falls back to `"other"`, so every listing has one and
 *    this never renders blank.
 *
 * The avatar is a plain `<img>`, not `next/image`: these are 40px marks from
 * many hosts, so routing them through the optimiser would add `remotePatterns`
 * config and per-image Worker cost for no visual gain. A failed load (deleted
 * account, renamed org) falls through to tiers 2 and 3 rather than leaving a
 * broken-image glyph.
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

/**
 * The GitHub owner's avatar URL, or null when the repository is not a GitHub
 * URL we can read an owner out of.
 *
 * `github.com/<owner>.png` is GitHub's own documented avatar redirect and
 * works for both users and organisations. Parsing goes through `URL` and an
 * exact host check rather than a substring match, so a hostile
 * `repository_url` such as `https://github.com.evil.test/x/y` cannot smuggle
 * in a third-party image host -- the value is publisher-supplied, and
 * `normalize.py` only guarantees it is http(s), not where it points.
 */
function githubAvatar(repositoryUrl: string | null): string | null {
  if (!repositoryUrl) return null;
  let parsed: URL;
  try {
    parsed = new URL(repositoryUrl);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:") return null;
  if (parsed.hostname !== "github.com" && parsed.hostname !== "www.github.com") return null;
  const owner = parsed.pathname.split("/").filter(Boolean)[0];
  if (!owner) return null;
  return `https://github.com/${encodeURIComponent(owner)}.png?size=160`;
}

export function ListingLogo({
  listing,
  className = "size-9",
}: {
  listing: Pick<Listing, "tags" | "categories" | "repositoryUrl">;
  className?: string;
}) {
  const [avatarFailed, setAvatarFailed] = useState(false);

  const avatar = githubAvatar(listing.repositoryUrl);
  const brand = brandTag(listing.tags);
  const category = listing.categories[0] ?? "other";
  const CategoryIcon = CATEGORY_ICONS[category] ?? FiGrid;

  return (
    <div
      className={`grid shrink-0 place-items-center overflow-hidden rounded-lg border border-border bg-muted/40 ${className}`}
    >
      {avatar && !avatarFailed ? (
        /* Decorative: the listing title sits directly beside this in every
           caller, so announcing the mark as well would just repeat it.

           The plain <img> is deliberate (see the note above the component):
           a 40px avatar from an arbitrary publisher's host would need
           `remotePatterns` config plus per-image Worker optimisation cost,
           for no visual gain at this size. */
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={avatar}
          alt=""
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setAvatarFailed(true)}
          className="size-full object-cover"
        />
      ) : brand ? (
        <BrandIcon name={brand} className="size-1/2" />
      ) : (
        <CategoryIcon className="size-1/2 text-muted-foreground" />
      )}
    </div>
  );
}
