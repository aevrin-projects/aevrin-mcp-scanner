"use client";

import { useCallback, useEffect, useState } from "react";
import { Bot, Loader2, Search, ShieldAlert } from "lucide-react";

import {
  AevrinMcpSnippet,
  browseListings,
  ITEM_TYPE_ICONS,
  ITEM_TYPE_LABELS,
  listCategories,
  ListingCard,
  listTypes,
  SORT_LABELS,
  type Category,
  type ItemType,
  type Listing,
  type MarketplaceSort,
  type TypeCount,
} from "@/entities/marketplace";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { EmptyState, PageHeader, Select } from "@/shared/ui";

/**
 * The Aevrin Registry: every kind of capability an agent can use, curated by
 * Aevrin administrators, browsable here and searchable by agents over MCP.
 *
 * Humans and agents search the same registry through the same endpoint, so
 * what this page shows for a query is what `search_registry` returns for it.
 *
 * The security filters (grade, price, client) appear only while browsing MCP
 * servers - the one type with a scanner. Offering "Grade B or better" on a
 * page of prompts would filter everything out and read as though prompts had
 * failed a check none of them was given.
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

const RAIL_SIZE = 3;

export function MarketplacePage() {
  const [items, setItems] = useState<Listing[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [types, setTypes] = useState<TypeCount[]>([]);
  const [rails, setRails] = useState<{ title: string; items: Listing[] }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [page, setPage] = useState(1);

  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [itemType, setItemType] = useState<ItemType | "">("");
  const [category, setCategory] = useState("");
  const [priceType, setPriceType] = useState("");
  const [minGrade, setMinGrade] = useState("");
  const [installTarget, setInstallTarget] = useState("");
  const [sort, setSort] = useState<MarketplaceSort>("recommended");

  const serversOnly = itemType === "mcp_server";
  const browsing = !query && !itemType && !category && !minGrade && !priceType && !installTarget;

  useEffect(() => {
    // Both are degraded filters if they fail, not a broken page: the
    // registry below renders regardless.
    listCategories().then(setCategories).catch(() => setCategories([]));
    listTypes().then(setTypes).catch(() => setTypes([]));
    void (async () => {
      const [featured, trending, recent] = await Promise.all([
        browseListings({ featured: true, pageSize: RAIL_SIZE }).catch(() => null),
        browseListings({ sort: "trending", pageSize: RAIL_SIZE }).catch(() => null),
        browseListings({ sort: "recently_added", pageSize: RAIL_SIZE }).catch(() => null),
      ]);
      setRails(
        [
          { title: "Featured", items: featured?.items ?? [] },
          { title: SORT_LABELS.trending, items: trending?.items ?? [] },
          { title: "Recently added", items: recent?.items ?? [] },
        ].filter((rail) => rail.items.length > 0),
      );
    })();
  }, []);

  const fetchPage = useCallback(
    async (nextPage: number) => {
      // The `await` comes first deliberately. Every setState below runs in an
      // async continuation rather than synchronously in the effect body,
      // which is what stops the cascading re-render React warns about.
      try {
        return await browseListings({
          q: query || undefined,
          type: itemType || undefined,
          category: category || undefined,
          // Server-only filters are never sent for other types, even if a
          // value is left over from browsing servers a moment ago.
          priceType: (serversOnly && priceType) || undefined,
          minGrade: (serversOnly && minGrade) || undefined,
          installTarget: (serversOnly && installTarget) || undefined,
          sort,
          page: nextPage,
        });
      } catch {
        return null;
      }
    },
    [query, itemType, category, priceType, minGrade, installTarget, sort, serversOnly],
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const result = await fetchPage(1);
      if (cancelled) return;
      if (!result) {
        setError("The registry could not be loaded. Try again in a moment.");
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
      setError("The registry could not be loaded. Try again in a moment.");
      setLoading(false);
      return;
    }
    setItems((current) => (append ? [...current, ...result.items] : result.items));
    setHasMore(result.hasMore);
    setPage(result.page);
    setLoading(false);
  }

  const total = types.reduce((sum, t) => sum + t.count, 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Aevrin Registry"
        description="MCP servers, skills, prompts, templates and more, curated by Aevrin. Browse them here, or let your agent search them through Aevrin MCP."
      />

      <details className="group rounded-lg border border-border bg-card">
        <summary className="flex cursor-pointer list-none items-center gap-3 p-4 text-sm font-medium [&::-webkit-details-marker]:hidden">
          <Bot className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          Use the registry from your agent
          <span className="ml-auto text-xs font-normal text-muted-foreground group-open:hidden">
            Show setup
          </span>
        </summary>
        <div className="border-t border-border p-4">
          <p className="mb-3 text-sm text-muted-foreground">
            Connect Aevrin MCP and your agent can search this registry by what you are trying to
            do, read an item, and use it. It only ever reads what is published here.
          </p>
          <AevrinMcpSnippet />
        </div>
      </details>

      {/* Not dismissible, and placed above the results rather than below. */}
      <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/40 p-4">
        <ShieldAlert className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          Popularity is not security. A server with thousands of stars can still be graded D. The
          grade comes from an Aevrin scan of MCP servers; the stars come from GitHub. Other item
          types are curated by an administrator and are not security-scanned.
        </p>
      </div>

      {types.length > 0 ? (
        // Padding inside the scroll container, not a negative margin: `-mx-1`
        // pushed the row 4px past the page edge and scrolled every viewport
        // sideways. The padding keeps the chips' focus rings from clipping.
        <div className="flex gap-2 overflow-x-auto p-1" role="group" aria-label="Item type">
          <TypeChip active={!itemType} onClick={() => setItemType("")} label="All" count={total} />
          {types.map(({ type, count }) => (
            <TypeChip
              key={type}
              active={itemType === type}
              onClick={() => setItemType(type)}
              label={ITEM_TYPE_LABELS[type]?.many ?? type}
              count={count}
              type={type}
            />
          ))}
        </div>
      ) : null}

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
            placeholder="Describe what you want to do, or search by name"
            className="pl-9"
            aria-label="Search the registry"
          />
        </div>

        <Select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Category">
          <option value="">All categories</option>
          {categories.map((item) => (
            <option key={item.slug} value={item.slug}>
              {item.name} ({item.count})
            </option>
          ))}
        </Select>

        {serversOnly ? (
          <>
            <Select value={minGrade} onChange={(event) => setMinGrade(event.target.value)} aria-label="Minimum security grade">
              {GRADE_FILTERS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </Select>
            <Select value={priceType} onChange={(event) => setPriceType(event.target.value)} aria-label="Pricing">
              {PRICE_FILTERS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </Select>
            <Select value={installTarget} onChange={(event) => setInstallTarget(event.target.value)} aria-label="Client compatibility">
              {TARGET_FILTERS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </Select>
          </>
        ) : null}

        <Select value={sort} onChange={(event) => setSort(event.target.value as MarketplaceSort)} aria-label="Sort by">
          {(Object.keys(SORT_LABELS) as MarketplaceSort[])
            // Sorting prompts "by security" would order them by a grade none
            // of them has.
            .filter((key) => key !== "security" || serversOnly)
            .map((key) => (
              <option key={key} value={key}>
                {SORT_LABELS[key]}
              </option>
            ))}
        </Select>

        <Button type="submit">Search</Button>
      </form>

      {browsing && rails.length > 0 ? (
        <div className="space-y-8">
          {rails.map((rail) => {
            // An id with spaces is several ids to aria-labelledby, which
            // would leave the section with no accessible name at all.
            const headingId = `rail-${rail.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
            return (
            <section key={rail.title} aria-labelledby={headingId}>
              <h2 id={headingId} className="mb-3 text-sm font-semibold">
                {rail.title}
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {rail.items.map((listing) => (
                  <ListingCard key={listing.id} listing={listing} />
                ))}
              </div>
            </section>
            );
          })}
          <h2 className="text-sm font-semibold">Everything</h2>
        </div>
      ) : null}

      {error ? (
        <EmptyState
          title="Could not load the registry"
          body={error}
          action={
            <Button onClick={() => void loadMore(1, false)} variant="outline">
              Try again
            </Button>
          }
        />
      ) : items.length === 0 && !loading ? (
        <EmptyState
          title="Nothing matches those filters"
          body={
            serversOnly
              ? "Try a broader search, or clear the grade filter to include servers that have not been graded."
              : "Try a broader search, or a different type or category."
          }
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
              <Button variant="outline" onClick={() => void loadMore(page + 1, true)} disabled={loading}>
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
          <span className="sr-only">Loading the registry</span>
        </div>
      ) : null}
    </div>
  );
}

function TypeChip({
  active,
  onClick,
  label,
  count,
  type,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count: number;
  type?: ItemType;
}) {
  const Icon = type ? ITEM_TYPE_ICONS[type] : null;
  return (
    <button
      type="button"
      onClick={onClick}
      // A toggle, stated as one, so assistive technology reports which type
      // is selected rather than a row of identical buttons.
      aria-pressed={active}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none ${
        active
          ? "border-foreground bg-foreground text-background"
          : "border-border bg-card text-foreground hover:border-foreground/30"
      }`}
    >
      {Icon ? <Icon className="size-3.5" aria-hidden="true" /> : null}
      {label}
      <span className={`tabular-nums text-xs ${active ? "opacity-80" : "text-muted-foreground"}`}>{count}</span>
    </button>
  );
}
