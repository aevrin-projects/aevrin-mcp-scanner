"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { Loader2, RefreshCw, Search, ShieldCheck } from "lucide-react";

import { marketplaceAdminApi } from "@/entities/admin";
import { ApiError } from "@/shared/api";
import { Button } from "@/shared/ui/button";
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

/**
 * Admin → Marketplace.
 *
 * Three things live here: the catalogue in every state, the submission queue,
 * and reports. Curation actions are editorial; the only security action is
 * "Force rescan", which starts a real scan and returns a real result.
 *
 * The scan button reports whether a scan actually ran or an existing result was
 * reused. An admin who pressed rescan and silently got a cached answer would
 * have no way to tell, and would draw the wrong conclusion from an unchanged
 * grade.
 */

interface Summary {
  total: number;
  scanned: number;
  unscanned: number;
  stale_scans: number;
  partial_coverage: number;
  grades: Record<string, number>;
  open_reports: number;
  pending_submissions: number;
}

type Row = Record<string, unknown> & {
  id: string;
  slug: string;
  title: string;
  status: string;
  security: { grade: string | null; score: number | null; state: string; label: string };
};

const STATUS_COLORS: Record<string, string> = {
  published: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400 border-emerald-500/20",
  review: "bg-amber-500/12 text-amber-700 dark:text-amber-400 border-amber-500/20",
  suspended: "bg-rose-500/12 text-rose-700 dark:text-rose-400 border-rose-500/20",
  rejected: "bg-rose-500/12 text-rose-700 dark:text-rose-400 border-rose-500/20",
  draft: "bg-muted text-muted-foreground border-transparent",
};

const GRADE_COLORS: Record<string, string> = {
  A: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400 border-emerald-500/20",
  B: "bg-sky-500/12 text-sky-700 dark:text-sky-400 border-sky-500/20",
  C: "bg-amber-500/12 text-amber-700 dark:text-amber-400 border-amber-500/20",
  D: "bg-rose-500/12 text-rose-700 dark:text-rose-400 border-rose-500/20",
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
  const [search, setSearch] = useState("");
  const [newUrl, setNewUrl] = useState("");

  const [reloadToken, setReloadToken] = useState(0);

  // Debounce search to avoid firing a fetch on every keystroke
  const [debouncedSearch, setDebouncedSearch] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const fetchAll = useCallback(async () => {
    const [s, list, subs, reps] = await Promise.all([
      marketplaceAdminApi.summary().catch(() => null),
      marketplaceAdminApi
        .list({
          status: statusFilter || undefined,
          grade: gradeFilter || undefined,
          q: debouncedSearch || undefined,
          limit: 50,
        })
        .catch(() => []),
      marketplaceAdminApi.submissions().catch(() => []),
      marketplaceAdminApi.reports().catch(() => []),
    ]);
    return { s, list, subs, reps };
  }, [statusFilter, gradeFilter, debouncedSearch]);

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

  if (loading && !summary) {
    return (
      <div className="flex items-center justify-center py-24 gap-2 text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        <span className="text-sm">Loading marketplace…</span>
        <span className="sr-only">Loading</span>
      </div>
    );
  }

  return (
    <MotionConfig reducedMotion="user">
      <div className="space-y-6">
        <PageHeader
          title="Marketplace"
          description="Catalogue, submissions, and reports."
        />

        {/* Metric row */}
        {summary ? (
          <motion.div
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={spring.moderate}
          >
            <MetricCard label="Listings" value={String(summary.total)} />
            <MetricCard
              label="Unscanned"
              value={String(summary.unscanned)}
              detail="No security evidence"
            />
            <MetricCard
              label="Stale scans"
              value={String(summary.stale_scans)}
              detail="Grade covers an older version"
            />
            <MetricCard
              label="Grade C or D"
              value={String((summary.grades.C ?? 0) + (summary.grades.D ?? 0))}
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
          <Panel>
            <PanelHeader>
              <PanelTitle>Add a server</PanelTitle>
            </PanelHeader>
            <PanelBody>
              <div className="flex flex-wrap items-end gap-3">
                <div className="min-w-[280px] flex-1">
                  <Input
                    value={newUrl}
                    onChange={(event) => setNewUrl(event.target.value)}
                    placeholder="https://github.com/owner/repo"
                    type="url"
                    aria-label="GitHub repository URL to add"
                  />
                </div>
                <Button
                  disabled={!newUrl.trim().startsWith("https://") || busyId === "new"}
                  onClick={() =>
                    void act(
                      "new",
                      () => marketplaceAdminApi.create({ source_url: newUrl.trim() }),
                      () => {
                        setNewUrl("");
                        return "Added. Scan it before publishing.";
                      },
                    )
                  }
                >
                  {busyId === "new" ? (
                    <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  ) : null}
                  Add
                </Button>
              </div>
              <p className="mt-3 text-xs text-muted-foreground">
                Runs the same URL validation a public submission does. Created
                for review, never published straight away.
              </p>
            </PanelBody>
          </Panel>

          {summary ? (
            <Panel className="lg:min-w-[200px]">
              <PanelHeader>
                <PanelTitle>Queue</PanelTitle>
              </PanelHeader>
              <PanelBody className="flex flex-col gap-3">
                <div className="flex items-center justify-between gap-4">
                  <span className="text-sm text-muted-foreground">Pending submissions</span>
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
            <PanelTitle>Catalogue</PanelTitle>
            {/* Filter/search bar — kept in the panel header so it scrolls with the panel */}
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
                  aria-label="Search listings by title"
                />
              </div>
              <Select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                aria-label="Filter by status"
                className="w-[140px]"
              >
                <option value="">Any status</option>
                {["published", "review", "suspended", "rejected", "draft"].map((s) => (
                  <option key={s} value={s}>
                    {s.charAt(0).toUpperCase() + s.slice(1)}
                  </option>
                ))}
              </Select>
              <Select
                value={gradeFilter}
                onChange={(e) => setGradeFilter(e.target.value)}
                aria-label="Filter by grade"
                className="w-[120px]"
              >
                <option value="">Any grade</option>
                {["A", "B", "C", "D"].map((g) => (
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
                <EmptyState title="No listings match" body="Try clearing the filters." />
              </div>
            ) : (
              <ScrollArea viewportClassName="max-h-[520px] overflow-y-auto scroll-fade">
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
                                href={`/marketplace/${row.slug}`}
                                className="truncate text-sm font-medium hover:underline"
                              >
                                {row.title}
                              </Link>
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
                                {row.security.score !== null ? ` · ${row.security.score}` : ""}
                              </span>
                            ) : (
                              <span className="text-xs text-muted-foreground">unscanned</span>
                            )}

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

                            {row.status === "published" ? (
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
                                        "suspended",
                                        "suspended by an administrator",
                                      ),
                                    () => "Suspended.",
                                  )
                                }
                              >
                                Suspend
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
                          </div>
                        </motion.div>
                      );
                    })}
                  </AnimatePresence>
                </div>
              </ScrollArea>
            )}
          </PanelBody>
        </Panel>

        {/* Submissions + Reports side by side on wider screens */}
        <div className="grid gap-4 lg:grid-cols-2">
          {/* Submissions */}
          <Panel>
            <PanelHeader>
              <PanelTitle>Submissions</PanelTitle>
              {submissions.length > 0 ? (
                <Badge variant="secondary" className="ms-auto">
                  {submissions.length} waiting
                </Badge>
              ) : null}
            </PanelHeader>
            <PanelBody className="p-0">
              {submissions.length === 0 ? (
                <div className="px-5 py-4">
                  <EmptyState title="Nothing waiting" body="Submitted servers appear here." />
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
                              {hasGrade ? `· Grade ${String(listing!.current_trust_grade)}` : "· not scanned"}
                            </p>
                          </div>
                          <div className="flex shrink-0 gap-2">
                            <Button
                              size="sm"
                              disabled={busyId === id || !hasGrade}
                              title={hasGrade ? undefined : "Scan this server before approving it"}
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
                                      "did not meet the marketplace criteria",
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
