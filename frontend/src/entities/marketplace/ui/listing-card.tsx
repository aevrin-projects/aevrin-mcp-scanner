import Link from "next/link";
import { Star } from "lucide-react";

import { Badge } from "@/shared/ui/badge";
import { PRICE_LABELS, type Listing } from "../model/types";
import { ListingLogo } from "./listing-logo";
import { PopularitySignals } from "./popularity-signals";
import { TypeBadge } from "./type-badge";

/**
 * One registry item, as a browse card.
 *
 * The registry is discovery only: a card describes what an item is and how
 * widely it is used, and makes no security claim. Popularity sits in the
 * footer in muted text, named for what it measures.
 */
export function ListingCard({ listing }: { listing: Listing }) {
  return (
    <Link
      href={`/marketplace/${listing.slug}`}
      className="group flex flex-col rounded-xl border border-border bg-card p-5 transition-colors hover:border-foreground/20 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <div className="flex min-w-0 items-start gap-3">
        <ListingLogo listing={listing} className="size-9" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate font-medium group-hover:underline">{listing.title}</h3>
            {listing.featured ? (
              <Star className="size-3.5 shrink-0 text-severity-medium" aria-label="Featured" />
            ) : null}
          </div>
          {listing.publisher ? (
            <p className="mt-0.5 truncate text-xs text-muted-foreground">{listing.publisher}</p>
          ) : null}
        </div>
      </div>

      <p className="mt-3 line-clamp-2 flex-1 text-sm text-muted-foreground">
        {listing.description || "No description provided."}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-1.5">
        <TypeBadge type={listing.itemType} />
        {listing.categories.slice(0, 2).map((category) => (
          <Badge key={category} variant="secondary" className="text-[11px]">
            {category.replace(/-/g, " ")}
          </Badge>
        ))}
        {listing.itemType === "mcp_server" ? (
          <Badge variant="outline" className="text-[11px]">
            {PRICE_LABELS[listing.priceType]}
          </Badge>
        ) : null}
        {listing.license ? (
          <Badge variant="outline" className="text-[11px]">
            {listing.license}
          </Badge>
        ) : null}
      </div>

      <div className="mt-4 border-t border-border pt-3">
        <PopularitySignals popularity={listing.popularity} />
      </div>
    </Link>
  );
}
