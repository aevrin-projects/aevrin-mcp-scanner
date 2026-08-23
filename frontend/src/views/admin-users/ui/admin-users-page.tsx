"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Search } from "lucide-react";
import { ApiError } from "@/shared/api";
import { StatusPill, adminApi } from "@/entities/admin";
import type { AdminUserPage } from "@/entities/admin";
import { Input } from "@/shared/ui/input";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { formatDate } from "@/shared/lib/format";

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "active", label: "Active" },
  { value: "disabled", label: "Disabled" },
  { value: "blocked", label: "Blocked" },
];

export function AdminUsersPage() {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<AdminUserPage | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Search and pagination happen server-side. Fetching every account and
  // filtering in the browser would be both slow and a needless exposure of
  // the whole customer list to the client.
  const load = useCallback(async () => {
    try {
      setData(await adminApi.listUsers({ q: query || undefined, status: statusFilter || undefined, page }));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load accounts.");
    }
  }, [query, statusFilter, page]);

  useEffect(() => {
    const id = window.setTimeout(() => void load(), 250); // debounce typing
    return () => window.clearTimeout(id);
  }, [load]);

  const pageCount = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Accounts</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {data ? `${data.total} account${data.total === 1 ? "" : "s"}` : "Loading…"}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-64 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            className="pl-9"
            placeholder="Search by email"
            aria-label="Search accounts by email"
          />
        </div>
        <div className="flex gap-1.5">
          {STATUS_FILTERS.map((f) => (
            <Button
              key={f.value || "all"}
              size="sm"
              variant={statusFilter === f.value ? "default" : "outline"}
              aria-pressed={statusFilter === f.value}
              onClick={() => {
                setStatusFilter(f.value);
                setPage(1);
              }}
            >
              {f.label}
            </Button>
          ))}
        </div>
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {!data ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      ) : data.rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border px-5 py-10 text-center text-sm text-muted-foreground">
          No accounts match.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full min-w-[820px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs tracking-[0.06em] text-muted-foreground uppercase">
                <th className="px-4 py-2.5 font-medium">Email</th>
                <th className="px-4 py-2.5 font-medium">Plan</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Scans</th>
                <th className="px-4 py-2.5 font-medium">Last scan</th>
                <th className="px-4 py-2.5 font-medium">Joined</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.user_id} className="border-b border-border/60 last:border-0 hover:bg-muted/30">
                  <td className="px-4 py-2.5">
                    <Link href={`/admin/users/${row.user_id}`} className="text-foreground hover:text-brand-text">
                      {row.email ?? row.user_id}
                    </Link>
                    {row.flagged ? (
                      <span className="ml-2 rounded-full border border-severity-medium/40 bg-severity-medium/10 px-1.5 py-0.5 text-[10px] text-severity-medium">
                        flagged
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="capitalize">{row.effective_tier}</span>
                    {/* Stored tier can outlive the paid period; effective is
                        what the product actually enforces, so show the drift
                        rather than only the flattering number. */}
                    {row.tier !== row.effective_tier ? (
                      <span className="ml-1.5 text-[11px] text-muted-foreground">(stored: {row.tier})</span>
                    ) : null}
                  </td>
                  <td className="px-4 py-2.5">
                    <StatusPill status={row.status} />
                  </td>
                  <td className="px-4 py-2.5 tabular-nums text-muted-foreground">{row.scans_this_period}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {row.last_scan_at ? formatDate(row.last_scan_at) : "-"}
                  </td>
                  <td className="px-4 py-2.5 text-muted-foreground">
                    {row.created_at ? formatDate(row.created_at) : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && pageCount > 1 ? (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            Page {data.page} of {pageCount}
          </span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <Button size="sm" variant="outline" disabled={page >= pageCount} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
