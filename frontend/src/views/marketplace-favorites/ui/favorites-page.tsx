"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";

import { ListingCard, listFavorites, type Listing } from "@/entities/marketplace";
import { buttonVariants } from "@/shared/ui/button";
import { EmptyState, PageHeader } from "@/shared/ui";

/** Saved servers, in the order they were saved. */
export function FavoritesPage() {
  const [items, setItems] = useState<Listing[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listFavorites()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="size-5 animate-spin text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">Loading</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Saved servers"
        description="Servers you have saved from the marketplace."
      />

      {items.length === 0 ? (
        <EmptyState
          title="Nothing saved yet"
          body="Save a server from its listing to keep it here."
          action={
            <Link href="/marketplace" className={buttonVariants({ variant: "outline" })}>
              Browse the marketplace
            </Link>
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((listing) => (
            <ListingCard key={listing.id} listing={listing} />
          ))}
        </div>
      )}
    </div>
  );
}
