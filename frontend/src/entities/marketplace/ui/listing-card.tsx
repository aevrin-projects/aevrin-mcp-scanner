import Link from "next/link";
import { Star } from "lucide-react";

import { Badge } from "@/shared/ui/badge";
import { PRICE_LABELS, type Listing } from "../model/types";
import { GradeBadge } from "./grade-badge";
import { PopularitySignals } from "./popularity-signals";

/**
 * One server, as a browse card.
 *
 * The layout puts the security grade and the popularity signals in visually
 * distinct regions — grade top-right in its own bordered tile, popularity
 * along the footer in muted text. That separation is doing real work: a
 * reader scanning a grid should never come away with the impression that a
 * high star count is the reason a card looks reassuring.
 */

export function ListingCard({ listing }: { listing: Listing }) {
  const { security, popularity } = listing;

  return (
    <Link
      href={`/marketplace/${listing.slug}`}
      className="group flex flex-col rounded-xl border border-border bg-card p-5 transition-colors hover:border-foreground/20 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <div className="flex items-start justify-between gap-4">
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

        {/* Security lives in its own tile, never inline with the metrics. */}
        <GradeBadge
          grade={security.grade}
          score={security.score}
          state={security.state}
          size="sm"
        />
      </div>

      <p className="mt-3 line-clamp-2 flex-1 text-sm text-muted-foreground">
        {listing.description || "No description provided."}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-1.5">
        {listing.categories.slice(0, 2).map((category) => (
          <Badge key={category} variant="secondary" className="text-[11px]">
            {category.replace(/-/g, " ")}
          </Badge>
        ))}
        <Badge variant="outline" className="text-[11px]">
          {PRICE_LABELS[listing.priceType]}
        </Badge>
        {listing.license ? (
          <Badge variant="outline" className="text-[11px]">
            {listing.license}
          </Badge>
        ) : null}
      </div>

      <div className="mt-4 flex items-center justify-between gap-3 border-t border-border pt-3">
        <PopularitySignals popularity={popularity} />
        {security.state !== "complete" ? (
          <span className="shrink-0 text-[11px] font-medium text-severity-medium">
            {security.state === "unscanned"
              ? "Unscanned"
              : security.state === "outdated"
                ? "Stale scan"
                : "Partial scan"}
          </span>
        ) : null}
      </div>
    </Link>
  );
}
