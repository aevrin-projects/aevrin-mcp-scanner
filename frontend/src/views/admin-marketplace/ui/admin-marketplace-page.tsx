"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { ChevronLeft, ChevronRight, Loader2, Plus, RefreshCw, Search, ShieldCheck } from "lucide-react";

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

import { CategoryManager } from "./category-manager";

/**
 * Admin → Registry: the control plane for the Aevrin Registry.
 *
 * The registry in every state, the suggestion queue, reports and categories.
 * Creating and editing an item happens in the item editor; this page is for
 * finding items and moving them through their lifecycle. Curation actions are
 * editorial; the only security action is "Rescan", which starts a real scan
 * and returns a real result.
 *
 * The scan button reports whether a scan actually ran or an existing result was
 * reused. An admin who pressed rescan and silently got a cached answer would
 * have no way to tell, and would draw the wrong conclusion from an unchanged
 * grade.
 */

const PAGE_SIZE = 30;

// The bulk regrade is not tied to a listing row, but `act` keys its busy state
// by id, so it gets a sentinel of its own rather than a second busy flag.
const REGRADE_ID = "__regrade_ungraded__";
// Mirrors REGRADE_BATCH_LIMIT in the marketplace controller. Shown in a
// tooltip only - the server enforces it, and the response says what remains.
const REGRADE_BATCH = 25;

interface Summary {
  total: number;
  scanned: number;
  unscanned: number;
  stale_scans: number;
  partial_coverage: number;
  grades: Record<string, number>;
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
  security: { grade: string | null; risk_score: number | null; state: string; label: string };
};

const STATUS_COLORS: Record<string, string> = {
  published: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400 border-emerald-500/20",
  review: "bg-amber-500/12 text-amber-700 dark:text-amber-400 border-amber-500/20",
  suspended: "bg-rose-500/12 text-rose-700 dark:text-rose-400 border-rose-500/20",
  rejected: "bg-rose-500/12 text-rose-700 dark:text-rose-400 border-rose-500/20",
  draft: "bg-muted text-muted-foreground border-transparent",
  archived: "bg-muted text-muted-foreground border-border",
};

const GRADE_COLORS: Record<string, string> = {
  A: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400 border-emerald-500/20",
  B: "bg-sky-500/12 text-sky-700 dark:text-sky-400 border-sky-500/20",
  C: "bg-amber-500/12 text-amber-700 dark:text-amber-400 border-amber-500/20",
  D: "bg-rose-500/12 text-rose-700 dark:text-rose-400 border-rose-500/20",
  F: "bg-rose-500/20 text-rose-800 dark:text-rose-300 border-rose-500/35",
};

export function AdminMarketplacePage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [submissions, setSubmissions] = useState<Record<string, unknown>[]>([]);
  const [reports, setReports] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState("");
  const [gradeFilter, setGradeFilter] = useState("");
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
          grade: gradeFilter || undefined,
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
  }, [statusFilter, gradeFilter, typeFilter, debouncedSearch, page]);

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

  /** Queue scans for the listings that carry no grade.
   *
   *  Bounded server-side, so this reports what is left rather than pretending
   *  one press fixed the whole catalogue. Skipped listings are named: a
   *  remote-only server with nothing to launch stays ungraded, and that is a
   *  result rather than a failure to retry.
   */
  async function regradeUngraded() {
    await act(
      REGRADE_ID,
      () => marketplaceAdminApi.regradeUngraded(),
      (r) => {
        const res = r as {
          queued: number;
          skipped: Array<{ listing: string; reason: string }>;
          remaining_ungraded: number;
        };
        const parts = [`Queued ${res.queued} scan${res.queued === 1 ? "" : "s"}.`];
        if (res.skipped.length) {
          parts.push(
            `${res.skipped.length} could not be scanned (${res.skipped[0].listing}: ${res.skipped[0].reason})`,
          );
        }
        if (res.remaining_ungraded > 0) {
          parts.push(`${res.remaining_ungraded} still ungraded. Run it again for the next batch.`);
        }
        return parts.join(" ");
      },
    );
  }

  async function act(id: string, fn: () => Promise<unknown>, describe: (r: unknown) => string) {
    setBusyId(id);
    setMessage(null);
    try {
      setMessage(describe(await fn()));
      setReloadToken((n) => n + 1);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "That action failed.");
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
            <Link href="/admin/marketplace/new" className={buttonVariants({ size: "sm" })}>
              <Plus className="size-4" aria-hidden="true" />
              New item
            </Link>
            <Button
              size="sm"
              variant="outline"
              disabled={busyId === REGRADE_ID || !summary?.unscanned}
              onClick={regradeUngraded}
              // Disabled with nothing ungraded rather than hidden: an admin
              // looking for this after an engine change needs to find it and
              // see that there is nothing to do, not wonder where it went.
              title={
                summary?.unscanned
                  ? `Queue scans for up to ${REGRADE_BATCH} ungraded listings`
                  : "Every listing already carries a grade"
              }
            >
              {busyId === REGRADE_ID ? (
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <ShieldCheck className="size-4" aria-hidden="true" />
              )}
              Rescan ungraded
            </Button>
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
            <MetricCard
              label="Ungraded servers"
              value={String(summary.unscanned)}
              detail="MCP servers with no grade"
            />
            <MetricCard
              label="Stale scans"
              value={String(summary.stale_scans)}
              detail="Grade covers an older version"
            />
            <MetricCard
              label="Grade C or worse"
              value={String((summary.grades.C ?? 0) + (summary.grades.D ?? 0) + (summary.grades.F ?? 0))}
            />
          </motion.div>
        ) : null}

        {/* Toast-style message */}
        <AnimatePresence mode="wait">
          {message ? (
            <motion.div
              key={message}
              className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={spring.fast}
            >
              {message}
            </motion.div>
          ) : null}
        </AnimatePresence>

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
              <Select
                value={gradeFilter}
                onChange={(e) => { setGradeFilter(e.target.value); setPage(0); }}
                aria-label="Filter by grade"
                className="w-[120px]"
              >
                <option value="">Any grade</option>
                {["A", "B", "C", "D", "F"].map((g) => (
                  <option key={g} value={g}>
                    Grade {g}
                  </option>
                ))}
              </Select>
            </div>
          </PanelHeader>

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
                        const gradeClass = row.security.grade ? GRADE_COLORS[row.security.grade] : "";
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
                              <p className="mt-0.5 text-xs text-muted-foreground">
                                {row.security.label}
                              </p>
                            </div>

                            {/* Grade chip + actions */}
                            <div className="flex shrink-0 items-center gap-2">
                              {row.security.grade ? (
                                <span
                                  className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold tabular-nums ${gradeClass}`}
                                >
                                  Grade {row.security.grade}
                                  {row.security.risk_score !== null ? ` · risk ${row.security.risk_score}` : ""}
                                </span>
                              ) : (
                                <span className="text-xs text-muted-foreground">
                                  {row.security.state === "not_applicable" ? "not scanned" : "no grade"}
                                </span>
                              )}

                              {(row.item_type ?? "mcp_server") === "mcp_server" ? (
                              <Button
                                size="sm"
                                variant="outline"
                                disabled={busyId === row.id}
                                aria-label={`Rescan ${row.title}`}
                                onClick={() =>
                                  void act(
                                    row.id,
                                    () => marketplaceAdminApi.scan(row.id, true),
                                    (r) => {
                                      const result = r as { reused: boolean; reason: string };
                                      return result.reused
                                        ? `No new scan: ${result.reason}`
                                        : `Scan started: ${result.reason}`;
                                    },
                                  )
                                }
                              >
                                {busyId === row.id ? (
                                  <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                                ) : (
                                  <RefreshCw className="size-3.5" aria-hidden="true" />
                                )}
                                Rescan
                              </Button>
                              ) : null}

                              {row.status === "archived" ? (
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  disabled={busyId === row.id}
                                  onClick={() =>
                                    void act(
                                      row.id,
                                      () => marketplaceAdminApi.setStatus(row.id, "draft", "restored"),
                                      () => "Restored to draft.",
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
                                      () =>
                                        marketplaceAdminApi.setStatus(
                                          row.id,
                                          "draft",
                                          "unpublished by an administrator",
                                        ),
                                      () => "Unpublished. It is a draft again.",
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
                                      () => marketplaceAdminApi.setStatus(row.id, "published"),
                                      () => "Published.",
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
                                      () => marketplaceAdminApi.setStatus(row.id, "archived", "archived"),
                                      () => "Archived.",
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
                      const hasGrade = Boolean(listing?.current_trust_grade);
                      return (
                        <div
                          key={id}
                          className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-5 py-3"
                        >
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium">
                              {(listing?.title as string) ?? String(submission.source_url)}
                            </p>
                            <p className="truncate text-xs text-muted-foreground">
                              {String(submission.source_url)}{" "}
                              {hasGrade ? `· Grade ${String(listing!.current_trust_grade)}` : "· no grade yet"}
                            </p>
                          </div>
                          <div className="flex shrink-0 gap-2">
                            {/* Not pre-checked here: the publish gate on the server is
                                the one definition of "may be published", and it says
                                why when it refuses. An MCP server must be scanned; it
                                need not be graded. */}
                            <Button
                              size="sm"
                              disabled={busyId === id}
                              onClick={() =>
                                void act(
                                  id,
                                  () => marketplaceAdminApi.decideSubmission(id, "approved"),
                                  () => "Approved and published.",
                                )
                              }
                            >
                              {busyId === id ? (
                                <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                              ) : (
                                <ShieldCheck className="size-3.5" aria-hidden="true" />
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
                                  () =>
                                    marketplaceAdminApi.decideSubmission(
                                      id,
                                      "rejected",
                                      "did not meet the registry's criteria",
                                    ),
                                  () => "Rejected.",
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
                                  () => marketplaceAdminApi.resolveReport(id, "dismissed"),
                                  () => "Dismissed.",
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
                                  () => marketplaceAdminApi.resolveReport(id, "actioned"),
                                  () => "Marked actioned.",
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
