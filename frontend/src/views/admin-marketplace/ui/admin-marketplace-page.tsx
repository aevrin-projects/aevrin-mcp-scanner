"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, RefreshCw } from "lucide-react";

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

  // A counter rather than a shared loader function: bumping it re-runs the
  // effect, and every state update then happens after an await rather than
  // synchronously in the effect body.
  const [reloadToken, setReloadToken] = useState(0);

  const fetchAll = useCallback(async () => {
    const [s, list, subs, reps] = await Promise.all([
      marketplaceAdminApi.summary().catch(() => null),
      marketplaceAdminApi
        .list({
          status: statusFilter || undefined,
          grade: gradeFilter || undefined,
          q: search || undefined,
          limit: 50,
        })
        .catch(() => []),
      marketplaceAdminApi.submissions().catch(() => []),
      marketplaceAdminApi.reports().catch(() => []),
    ]);
    return { s, list, subs, reps };
  }, [statusFilter, gradeFilter, search]);

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
      <div className="flex justify-center py-20">
        <Loader2 className="size-5 animate-spin text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">Loading</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Marketplace"
        description="Catalogue, submissions, and reports."
      />

      {summary ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
        </div>
      ) : null}

      {message ? (
        <div className="rounded-lg border border-border bg-muted/40 p-3 text-sm">{message}</div>
      ) : null}

      <Panel>
        <PanelHeader>
          <PanelTitle>Add a server</PanelTitle>
        </PanelHeader>
        <PanelBody className="flex flex-wrap items-end gap-3">
          <div className="min-w-[280px] flex-1">
            <Input
              value={newUrl}
              onChange={(event) => setNewUrl(event.target.value)}
              placeholder="https://github.com/owner/repo"
              type="url"
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
            Add
          </Button>
          <p className="w-full text-xs text-muted-foreground">
            Runs the same URL validation a public submission does. It is created
            for review, never published straight away.
          </p>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader>
          <PanelTitle>Catalogue</PanelTitle>
        </PanelHeader>
        <PanelBody className="space-y-4">
          <div className="flex flex-wrap gap-3">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by title"
              className="max-w-xs"
            />
            <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">Any status</option>
              {["published", "review", "suspended", "rejected", "draft"].map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
            <Select value={gradeFilter} onChange={(e) => setGradeFilter(e.target.value)}>
              <option value="">Any grade</option>
              {["A", "B", "C", "D"].map((g) => (
                <option key={g} value={g}>
                  Grade {g}
                </option>
              ))}
            </Select>
          </div>

          {rows.length === 0 ? (
            <EmptyState title="No listings match" body="Try clearing the filters." />
          ) : (
            <div className="space-y-2">
              {rows.map((row) => (
                <div
                  key={row.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border p-3"
                >
                  <div className="min-w-0 flex-1">
                    <Link
                      href={`/marketplace/${row.slug}`}
                      className="truncate text-sm font-medium hover:underline"
                    >
                      {row.title}
                    </Link>
                    <p className="text-xs text-muted-foreground">
                      {row.status} ·{" "}
                      {row.security.grade
                        ? `Grade ${row.security.grade} (${row.security.score}/100)`
                        : "unscanned"}{" "}
                      · {row.security.label}
                    </p>
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busyId === row.id}
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
                      <RefreshCw className="size-3.5" aria-hidden="true" />
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
                </div>
              ))}
            </div>
          )}
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader>
          <PanelTitle>Submissions awaiting review ({submissions.length})</PanelTitle>
        </PanelHeader>
        <PanelBody>
          {submissions.length === 0 ? (
            <EmptyState title="Nothing waiting" body="Submitted servers appear here." />
          ) : (
            <div className="space-y-2">
              {submissions.map((submission) => {
                const id = String(submission.id);
                const listing = submission.listing as Record<string, unknown> | null;
                return (
                  <div
                    key={id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border p-3"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">
                        {(listing?.title as string) ?? String(submission.source_url)}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {String(submission.source_url)} ·{" "}
                        {listing?.current_trust_grade
                          ? `Grade ${listing.current_trust_grade}`
                          : "not scanned"}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        size="sm"
                        disabled={busyId === id || !listing?.current_trust_grade}
                        title={
                          listing?.current_trust_grade
                            ? undefined
                            : "Scan this server before publishing it"
                        }
                        onClick={() =>
                          void act(
                            id,
                            () => marketplaceAdminApi.decideSubmission(id, "approved"),
                            () => "Approved and published.",
                          )
                        }
                      >
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
          )}
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader>
          <PanelTitle>Open reports ({reports.length})</PanelTitle>
        </PanelHeader>
        <PanelBody>
          {reports.length === 0 ? (
            <EmptyState title="No open reports" body="Reports from users appear here." />
          ) : (
            <div className="space-y-2">
              {reports.map((report) => {
                const id = String(report.id);
                const listing = report.listing as Record<string, unknown> | null;
                return (
                  <div
                    key={id}
                    className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-border p-3"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">
                        {String(report.kind) === "security" ? "Security: " : ""}
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
                        Action
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </PanelBody>
      </Panel>
    </div>
  );
}
