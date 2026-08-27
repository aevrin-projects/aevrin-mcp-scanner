"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Search, ShieldAlert } from "lucide-react";

import {
  browseListings,
  listCategories,
  ListingCard,
  SORT_LABELS,
  type Category,
  type Listing,
  type MarketplaceSort,
} from "@/entities/marketplace";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { EmptyState, PageHeader, Select } from "@/shared/ui";

/**
 * Discover: browse, search, filter, sort.
 *
 * The filter row includes a security filter alongside the category one, and
 * both are given equal visual weight. That is deliberate — a marketplace that
 * lets you narrow by "database" but not by "at least a B" has decided which
 * of those questions matters, and it has decided wrong for this product.
 *
 * The banner beneath the header is permanent rather than dismissible. It is
 * the one sentence that stops someone reading a 25,000-star card as a safety
 * endorsement, and a reader who has not seen it before is exactly the reader
 * who needs it.
 */

const PRICE_FILTERS = [
  { value: "", label: "Any price" },
  { value: "open_source", label: "Open source" },
  { value: "free", label: "Free" },
  { value: "freemium", label: "Freemium" },
  { value: "paid", label: "Paid" },
];

const GRADE_FILTERS = [
  { value: "", label: "Any grade" },
  { value: "A", label: "Grade A only" },
  { value: "B", label: "Grade B or better" },
  { value: "C", label: "Grade C or better" },
];

const TARGET_FILTERS = [
  { value: "", label: "Any client" },
  { value: "claude-code", label: "Claude Code" },
  { value: "codex", label: "Codex" },
  { value: "cursor", label: "Cursor" },
  { value: "generic", label: "Generic MCP" },
];

export function MarketplacePage() {
  const [items, setItems] = useState<Listing[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [page, setPage] = useState(1);

  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [priceType, setPriceType] = useState("");
  const [minGrade, setMinGrade] = useState("");
  const [installTarget, setInstallTarget] = useState("");
  const [sort, setSort] = useState<MarketplaceSort>("recommended");

  useEffect(() => {
    listCategories()
      .then(setCategories)
      // A failed category list is a degraded filter, not a broken page. The
      // catalogue below renders regardless.
      .catch(() => setCategories([]));
  }, []);

  const fetchPage = useCallback(
    async (nextPage: number) => {
      // The `await` comes first deliberately. Every setState below runs in an
      // async continuation rather than synchronously in the effect body,
      // which is what stops the cascading re-render React warns about.
      try {
        const result = await browseListings({
          q: query || undefined,
          category: category || undefined,
          priceType: priceType || undefined,
          minGrade: minGrade || undefined,
          installTarget: installTarget || undefined,
          sort,
          page: nextPage,
        });
        return result;
      } catch {
        return null;
      }
    },
    [query, category, priceType, minGrade, installTarget, sort],
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const result = await fetchPage(1);
      if (cancelled) return;
      if (!result) {
        setError("The marketplace could not be loaded. Try again in a moment.");
        setLoading(false);
        return;
      }
      setError(null);
      setItems(result.items);
      setHasMore(result.hasMore);
      setPage(result.page);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [fetchPage]);

  /** "Load more" and "Try again": user events, so setting state up front here
   *  is exactly what React expects. */
  async function loadMore(nextPage: number, append: boolean) {
    setLoading(true);
    setError(null);
    const result = await fetchPage(nextPage);
    if (!result) {
      setError("The marketplace could not be loaded. Try again in a moment.");
      setLoading(false);
      return;
    }
    setItems((current) => (append ? [...current, ...result.items] : result.items));
    setHasMore(result.hasMore);
    setPage(result.page);
    setLoading(false);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="MCP marketplace"
        description="Browse MCP servers from the official registry, scanned by Aevrin before you install them."
      />

      {/* Not dismissible, and placed above the results rather than below. */}
      <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/40 p-4">
        <ShieldAlert className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          Popularity is not security. A server with thousands of stars can still
          be graded D. The grade comes from an Aevrin scan; the stars come from
          GitHub. They are shown separately because they answer different
          questions.
        </p>
      </div>

      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          setQuery(search.trim());
        }}
      >
        <div className="relative min-w-[240px] flex-1">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search servers, publishers, capabilities"
            className="pl-9"
            aria-label="Search the marketplace"
          />
        </div>

        <Select
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          aria-label="Category"
        >
          <option value="">All categories</option>
          {categories.map((item) => (
            <option key={item.slug} value={item.slug}>
              {item.name} ({item.count})
            </option>
          ))}
        </Select>

        <Select
          value={minGrade}
          onChange={(event) => setMinGrade(event.target.value)}
          aria-label="Minimum security grade"
        >
          {GRADE_FILTERS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </Select>

        <Select
          value={priceType}
          onChange={(event) => setPriceType(event.target.value)}
          aria-label="Pricing"
        >
          {PRICE_FILTERS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </Select>

        <Select
          value={installTarget}
          onChange={(event) => setInstallTarget(event.target.value)}
          aria-label="Client compatibility"
        >
          {TARGET_FILTERS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </Select>

        <Select
          value={sort}
          onChange={(event) => setSort(event.target.value as MarketplaceSort)}
          aria-label="Sort by"
        >
          {(Object.keys(SORT_LABELS) as MarketplaceSort[]).map((key) => (
            <option key={key} value={key}>
              {SORT_LABELS[key]}
            </option>
          ))}
        </Select>

        <Button type="submit">Search</Button>
      </form>

      {error ? (
        <EmptyState
          title="Could not load the marketplace"
          body={error}
          action={
            <Button onClick={() => void loadMore(1, false)} variant="outline">
              Try again
            </Button>
          }
        />
      ) : items.length === 0 && !loading ? (
        <EmptyState
          title="No servers match those filters"
          body="Try a broader search, or clear the grade filter to include servers that have not been scanned yet."
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((listing) => (
              <ListingCard key={listing.id} listing={listing} />
            ))}
          </div>

          {hasMore ? (
            <div className="flex justify-center pt-2">
              <Button
                variant="outline"
                onClick={() => void loadMore(page + 1, true)}
                disabled={loading}
              >
                {loading ? (
                  <>
                    <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                    Loading
                  </>
                ) : (
                  "Load more"
                )}
              </Button>
            </div>
          ) : null}
        </>
      )}

      {loading && items.length === 0 ? (
        <div className="flex justify-center py-12">
          <Loader2 className="size-5 animate-spin text-muted-foreground" aria-hidden="true" />
          <span className="sr-only">Loading the marketplace</span>
        </div>
      ) : null}
    </div>
  );
}
