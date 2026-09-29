"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { Check, ChevronLeft, ChevronRight, Loader2, Plus, Search } from "lucide-react";

import { marketplaceAdminApi } from "@/entities/admin";
import { ITEM_TYPE_LABELS, ITEM_TYPES, TypeBadge, type ItemType } from "@/entities/marketplace";
import { ApiError } from "@/shared/api";
import { Button, buttonVariants } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import {
  EmptyState,
  MetricCard,
  PageHeader,
  Panel,
  PanelBody,
  PanelHeader,
  PanelTitle,
  Select,
} from "@/shared/ui";
import { Badge } from "@/shared/ui/badge";
import { spring } from "@/lib/springs";
import { ScrollArea } from "@/components/ui/scroll-area";

import { BulkPublishControl } from "./bulk-publish-control";
import { CategoryManager } from "./category-manager";

/**
 * Admin → Registry: the control plane for the Aevrin Registry.
 *
 * The registry in every state, the suggestion queue, reports and categories.
 * Creating and editing an item happens in the item editor; this page is for
 * finding items and moving them through their lifecycle. Every action here is
 * editorial: the registry is discovery only and holds no scan result.
 */

const PAGE_SIZE = 30;

interface Summary {
  total: number;
  statuses: Record<string, number>;
  types: Record<string, number>;
  open_reports: number;
  pending_submissions: number;
}

type Row = Record<string, unknown> & {
  id: string;
  slug: string;
  title: string;
  status: string;
  item_type: ItemType;
};

type PanelName = "items" | "suggestions" | "reports";

/** The result of the last row action, shown in the panel it was taken in. */
interface Outcome {
  panel: PanelName;
  tone: "success" | "error";
  text: string;
  /** On a refused publish or approval: the item's editor, where the missing
   *  field can be added before trying again. */
  editHref?: string;
}

const STATUS_COLORS: Record<string, string> = {
  published: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400 border-emerald-500/20",
  review: "bg-amber-500/12 text-amber-700 dark:text-amber-400 border-amber-500/20",
  suspended: "bg-rose-500/12 text-rose-700 dark:text-rose-400 border-rose-500/20",
  rejected: "bg-rose-500/12 text-rose-700 dark:text-rose-400 border-rose-500/20",
  draft: "bg-muted text-muted-foreground border-transparent",
  archived: "bg-muted text-muted-foreground border-border",
};

export function AdminMarketplacePage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [submissions, setSubmissions] = useState<Record<string, unknown>[]>([]);
  const [reports, setReports] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [search, setSearch] = useState("");

  const [reloadToken, setReloadToken] = useState(0);
  const [page, setPage] = useState(0);

  // Debounce search to avoid firing a fetch on every keystroke
  const [debouncedSearch, setDebouncedSearch] = useState("");
  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(0);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const fetchAll = useCallback(async () => {
    const [s, list, subs, reps] = await Promise.all([
      marketplaceAdminApi.summary().catch(() => null),
      marketplaceAdminApi
        .list({
          status: statusFilter || undefined,
          type: typeFilter || undefined,
          q: debouncedSearch || undefined,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        })
        .catch(() => []),
      marketplaceAdminApi.submissions().catch(() => []),
      marketplaceAdminApi.reports().catch(() => []),
    ]);
    return { s, list, subs, reps };
  }, [statusFilter, typeFilter, debouncedSearch, page]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const { s, list, subs, reps } = await fetchAll();
      if (cancelled) return;
      setSummary(s as Summary | null);
      setRows(list as Row[]);
      setSubmissions(subs);
      setReports(reps);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [fetchAll, reloadToken]);

  // The result used to go to a toast at the top of the page, far above the
  // Suggestions and Reports panels, so a refused approval looked like a
  // button that did nothing. It now appears in the panel the action was
  // taken in, in that panel's live region, naming the item.
  async function act(
    id: string,
    target: { panel: PanelName; label: string; editHref?: string },
    fn: () => Promise<unknown>,
    success: string,
  ) {
    setBusyId(id);
    setOutcome(null);
    try {
      await fn();
      setOutcome({ panel: target.panel, tone: "success", text: `${target.label}: ${success}` });
      setReloadToken((n) => n + 1);
    } catch (error) {
      setOutcome({
        panel: target.panel,
        tone: "error",
        text: `${target.label}: ${error instanceof ApiError ? error.message : "that action failed."}`,
        editHref: target.editHref,
      });
    } finally {
      setBusyId(null);
    }
  }

  // The page header stays put while the catalogue loads. Returning a bare
  // spinner removed the <h1> entirely, so the page had no title, no landmark
  // heading and nothing for a screen reader to announce until the fetch
  // resolved - and it made the whole panel flicker between two layouts.
  if (loading && !summary) {
    return (
      <>
        <PageHeader
          pretitle="Administration"
          title="Registry"
          description="Every item in every state, suggestions, reports, and categories."
        />
        <div className="flex items-center justify-center gap-2 py-24 text-muted-foreground" aria-busy>
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          <span className="text-sm">Loading the registry…</span>
        </div>
      </>
    );
  }

  return (
    <MotionConfig reducedMotion="user">
      <div className="space-y-6">
        <PageHeader
          pretitle="Administration"
          title="Registry"
          description="Every item in every state, suggestions, reports, and categories."
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <BulkPublishControl onPublished={() => setReloadToken((n) => n + 1)} />
              <Link href="/admin/marketplace/new" className={buttonVariants({ size: "sm" })}>
                <Plus className="size-4" aria-hidden="true" />
                New item
              </Link>
            </div>
          }
        />

        {/* Metric row */}
        {summary ? (
          <motion.div
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={spring.moderate}
          >
            <MetricCard label="Items" value={String(summary.total)} detail={`${summary.statuses.published ?? 0} published`} />
            <MetricCard label="Drafts" value={String(summary.statuses.draft ?? 0)} detail="Not yet published" />
            <MetricCard label="MCP servers" value={String(summary.types.mcp_server ?? 0)} />
            <MetricCard label="Other types" value={String(summary.total - (summary.types.mcp_server ?? 0))} />
          </motion.div>
        ) : null}

        {/* Top row: Add server + quick stats side-by-side on wider screens */}
        <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
          <CategoryManager onChanged={() => setReloadToken((n) => n + 1)} />

          {summary ? (
            <Panel className="lg:min-w-[200px]">
              <PanelHeader>
                <PanelTitle>Queue</PanelTitle>
              </PanelHeader>
              <PanelBody className="flex flex-col gap-3">
                <div className="flex items-center justify-between gap-4">
                  <span className="text-sm text-muted-foreground">Pending suggestions</span>
                  <span className="text-sm font-semibold tabular-nums">{summary.pending_submissions}</span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span className="text-sm text-muted-foreground">Open reports</span>
                  <span className="text-sm font-semibold tabular-nums">{summary.open_reports}</span>
                </div>
              </PanelBody>
            </Panel>
          ) : null}
        </div>

        {/* Catalogue */}
        <Panel>
          <PanelHeader className="flex-wrap gap-y-3">
            <PanelTitle>Items</PanelTitle>
            {/* Filter/search bar, kept in the panel header so it scrolls with the panel */}
            <div className="ms-auto flex flex-wrap items-center gap-2">
              {/* Search */}
              <div className="relative">
                <Search
                  className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
                  aria-hidden="true"
                />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search by title"
                  className="pl-8 w-[180px]"
                  aria-label="Search items by title"
                />
              </div>
              <Select
                value={typeFilter}
                onChange={(e) => { setTypeFilter(e.target.value); setPage(0); }}
                aria-label="Filter by type"
                className="w-[150px]"
              >
                <option value="">Any type</option>
                {ITEM_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {ITEM_TYPE_LABELS[type].one}
                  </option>
                ))}
              </Select>
              <Select
                value={statusFilter}
                onChange={(e) => { setStatusFilter(e.target.value); setPage(0); }}
                aria-label="Filter by status"
                className="w-[140px]"
              >
                <option value="">Any status</option>
                {["published", "draft", "review", "suspended", "rejected", "archived"].map((s) => (
                  <option key={s} value={s}>
                    {s.charAt(0).toUpperCase() + s.slice(1)}
                  </option>
                ))}
              </Select>
            </div>
          </PanelHeader>

          <ActionOutcome panel="items" outcome={outcome} />

          <PanelBody className="p-0">
            {rows.length === 0 ? (
              <div className="px-5 py-4">
                <EmptyState title="No items match" body="Try clearing the filters, or create a new item." />
              </div>
            ) : (
              <>
                <ScrollArea viewportClassName="overflow-y-auto scroll-fade">
                  <div className="divide-y divide-border">
                    <AnimatePresence initial={false}>
                      {rows.map((row) => {
                        const statusClass = STATUS_COLORS[row.status] ?? "bg-muted text-muted-foreground border-transparent";
                        return (
                          <motion.div
                            key={row.id}
                            layout
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={spring.fast}
                            className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-5 py-3"
                          >
                            {/* Identity */}
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <Link
                                  href={`/admin/marketplace/${row.id}`}
                                  className="truncate text-sm font-medium hover:underline"
                                >
                                  {row.title}
                                </Link>
                                <TypeBadge type={row.item_type ?? "mcp_server"} />
                                <span
                                  className={`inline-flex items-center rounded-md border px-1.5 py-0 text-[11px] font-medium ${statusClass}`}
                                >
                                  {row.status}
                                </span>
                              </div>
                              <p className="mt-0.5 truncate text-xs text-muted-foreground">{row.slug}</p>
                            </div>

                            {/* Lifecycle actions */}
                            <div className="flex shrink-0 items-center gap-2">
                              {row.status === "archived" ? (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  disabled={busyId === row.id}
                                  onClick={() =>
                                    void act(
                                      row.id,
                                      { panel: "items", label: row.title },
                                      () => marketplaceAdminApi.setStatus(row.id, "draft", "restored"),
                                      "restored to draft.",
                                    )
                                  }
                                >
                                  Restore
                                </Button>
                              ) : row.status === "published" ? (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  disabled={busyId === row.id}
                                  onClick={() =>
                                    void act(
                                      row.id,
                                      { panel: "items", label: row.title },
                                      () =>
                                        marketplaceAdminApi.setStatus(
                                          row.id,
                                          "draft",
                                          "unpublished by an administrator",
                                        ),
                                      "unpublished. It is a draft again.",
                                    )
                                  }
                                >
                                  Unpublish
                                </Button>
                              ) : (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  disabled={busyId === row.id}
                                  onClick={() =>
                                    void act(
                                      row.id,
                                      {
                                        panel: "items",
                                        label: row.title,
                                        editHref: `/admin/marketplace/${row.id}`,
                                      },
                                      () => marketplaceAdminApi.setStatus(row.id, "published"),
                                      "published.",
                                    )
                                  }
                                >
                                  Publish
                                </Button>
                              )}

                              {row.status !== "archived" ? (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  disabled={busyId === row.id}
                                  aria-label={`Archive ${row.title}`}
                                  onClick={() =>
                                    void act(
                                      row.id,
                                      { panel: "items", label: row.title },
                                      () => marketplaceAdminApi.setStatus(row.id, "archived", "archived"),
                                      "archived.",
                                    )
                                  }
                                >
                                  Archive
                                </Button>
                              ) : null}
                            </div>
                          </motion.div>
                        );
                      })}
                    </AnimatePresence>
                  </div>
                </ScrollArea>

                {/* Pagination controls */}
                <div className="flex items-center justify-between border-t border-border px-5 py-3">
                  <span className="text-xs text-muted-foreground tabular-nums">
                    Page {page + 1}
                    {rows.length < PAGE_SIZE && page === 0 ? ` · ${rows.length} total` : ""}
                  </span>
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={page === 0}
                      aria-label="Previous page"
                      onClick={() => setPage((p) => p - 1)}
                    >
                      <ChevronLeft className="size-4" aria-hidden="true" />
                      Prev
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={rows.length < PAGE_SIZE}
                      aria-label="Next page"
                      onClick={() => setPage((p) => p + 1)}
                    >
                      Next
                      <ChevronRight className="size-4" aria-hidden="true" />
                    </Button>
                  </div>
                </div>
              </>
            )}
          </PanelBody>
        </Panel>

        {/* Submissions + Reports side by side on wider screens */}
        <div className="grid gap-4 lg:grid-cols-2">
          {/* Submissions */}
          <Panel>
            <PanelHeader>
              <PanelTitle>Suggestions</PanelTitle>
              {submissions.length > 0 ? (
                <Badge variant="secondary" className="ms-auto">
                  {submissions.length} waiting
                </Badge>
              ) : null}
            </PanelHeader>
            <ActionOutcome panel="suggestions" outcome={outcome} />
            <PanelBody className="p-0">
              {submissions.length === 0 ? (
                <div className="px-5 py-4">
                  <EmptyState title="Nothing waiting" body="Items users suggest appear here." />
                </div>
              ) : (
                <ScrollArea viewportClassName="max-h-[360px] overflow-y-auto scroll-fade">
                  <div className="divide-y divide-border">
                    {submissions.map((submission) => {
                      const id = String(submission.id);
                      const listing = submission.listing as Record<string, unknown> | null;
                      const label = (listing?.title as string) ?? String(submission.source_url);
                      const listingId = submission.listing_id ? String(submission.listing_id) : null;
                      const target = {
                        panel: "suggestions" as const,
                        label,
                        editHref: listingId ? `/admin/marketplace/${listingId}` : undefined,
                      };
                      return (
                        <div
                          key={id}
                          className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-5 py-3"
                        >
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium">{label}</p>
                            <p className="truncate text-xs text-muted-foreground">
                              {String(submission.source_url)}
                            </p>
                          </div>
                          <div className="flex shrink-0 gap-2">
                            {/* Not pre-checked here: the publish gate on the server is
                                the one definition of "may be published", and it says
                                why when it refuses. */}
                            <Button
                              size="sm"
                              disabled={busyId === id}
                              onClick={() =>
                                void act(
                                  id,
                                  target,
                                  () => marketplaceAdminApi.decideSubmission(id, "approved"),
                                  "approved and published.",
                                )
                              }
                            >
                              {busyId === id ? (
                                <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                              ) : (
                                <Check className="size-3.5" aria-hidden="true" />
                              )}
                              Approve
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              disabled={busyId === id}
                              onClick={() =>
                                void act(
                                  id,
                                  target,
                                  () =>
                                    marketplaceAdminApi.decideSubmission(
                                      id,
                                      "rejected",
                                      "did not meet the registry's criteria",
                                    ),
                                  "rejected.",
                                )
                              }
                            >
                              Reject
                            </Button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </ScrollArea>
              )}
            </PanelBody>
          </Panel>

          {/* Reports */}
          <Panel>
            <PanelHeader>
              <PanelTitle>Open reports</PanelTitle>
              {reports.length > 0 ? (
                <Badge variant="secondary" className="ms-auto">
                  {reports.length} open
                </Badge>
              ) : null}
            </PanelHeader>
            <ActionOutcome panel="reports" outcome={outcome} />
            <PanelBody className="p-0">
              {reports.length === 0 ? (
                <div className="px-5 py-4">
                  <EmptyState title="No open reports" body="Reports from users appear here." />
                </div>
              ) : (
                <ScrollArea viewportClassName="max-h-[360px] overflow-y-auto scroll-fade">
                  <div className="divide-y divide-border">
                    {reports.map((report) => {
                      const id = String(report.id);
                      const listing = report.listing as Record<string, unknown> | null;
                      const target = {
                        panel: "reports" as const,
                        label: `Report on ${(listing?.title as string) ?? "an unknown listing"}`,
                      };
                      return (
                        <div
                          key={id}
                          className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 px-5 py-3"
                        >
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium">
                              {String(report.kind) === "security" ? (
                                <span className="text-rose-600 dark:text-rose-400">Security: </span>
                              ) : null}
                              {String(report.reason)}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {(listing?.title as string) ?? "unknown listing"}
                            </p>
                          </div>
                          <div className="flex shrink-0 gap-2">
                            <Button
                              size="sm"
                              variant="ghost"
                              disabled={busyId === id}
                              onClick={() =>
                                void act(
                                  id,
                                  target,
                                  () => marketplaceAdminApi.resolveReport(id, "dismissed"),
                                  "dismissed.",
                                )
                              }
                            >
                              Dismiss
                            </Button>
                            <Button
                              size="sm"
                              disabled={busyId === id}
                              onClick={() =>
                                void act(
                                  id,
                                  target,
                                  () => marketplaceAdminApi.resolveReport(id, "actioned"),
                                  "marked actioned.",
                                )
                              }
                            >
                              {busyId === id ? (
                                <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                              ) : null}
                              Action
                            </Button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </ScrollArea>
              )}
            </PanelBody>
          </Panel>
        </div>
      </div>
    </MotionConfig>
  );
}

/**
 * A panel's live region. Always mounted, so a screen reader announces the
 * text when it appears; empty unless the last action was taken in this panel,
 * so a result is announced once, in one place.
 */
function ActionOutcome({ panel, outcome }: { panel: PanelName; outcome: Outcome | null }) {
  const mine = outcome?.panel === panel ? outcome : null;
  return (
    <div role="status" aria-live="polite" className={mine ? "border-b border-border px-5 py-3" : undefined}>
      {mine ? (
        <p
          className={
            mine.tone === "error"
              ? "text-sm text-rose-700 dark:text-rose-300"
              : "text-sm text-emerald-700 dark:text-emerald-400"
          }
        >
          <span className="font-medium">{mine.tone === "error" ? "Not done. " : "Done. "}</span>
          {mine.text}
          {mine.tone === "error" && mine.editHref ? (
            <>
              {" "}
              <Link href={mine.editHref} className="font-medium underline underline-offset-2">
                Edit
              </Link>
            </>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}
