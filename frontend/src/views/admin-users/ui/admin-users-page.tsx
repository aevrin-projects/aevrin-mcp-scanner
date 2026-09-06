"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Search, X } from "lucide-react";
import { ApiError } from "@/shared/api";
import { StatusPill, adminApi } from "@/entities/admin";
import type { AdminUserPage } from "@/entities/admin";
import { Alert, AlertDescription } from "@/shared/ui/alert";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { EmptyState } from "@/shared/ui/empty-state";
import { Input } from "@/shared/ui/input";
import { PageHeader } from "@/shared/ui/page-header";
import { Panel, PanelTableWrap } from "@/shared/ui/panel";
import { Skeleton } from "@/shared/ui/skeleton";
import { TBody, TD, TH, THead, TR, Table } from "@/shared/ui/data-table";
import { TablePagination } from "@/shared/ui/table-pagination";
import { formatDate } from "@/shared/lib/format";

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "active", label: "Active" },
  { value: "disabled", label: "Disabled" },
  { value: "blocked", label: "Blocked" },
] as const;

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
  const filtered = Boolean(query || statusFilter);

  return (
    <>
      <PageHeader
        pretitle="Administration"
        title="Accounts"
        description="Every Aevrin account, with the plan the product actually enforces and the standing it is in."
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative w-full sm:max-w-xs">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            className="h-8 pl-9"
            placeholder="Search by email"
            aria-label="Search accounts by email"
          />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
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
          {filtered ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setQuery("");
                setStatusFilter("");
                setPage(1);
              }}
            >
              Reset
              <X className="size-4" />
            </Button>
          ) : null}
        </div>
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {!data ? (
        <div className="space-y-2" aria-busy>
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-12 rounded-lg" />
          ))}
        </div>
      ) : data.rows.length === 0 ? (
        <EmptyState
          title="No accounts match"
          body={
            filtered
              ? "Nothing matches this search and filter. Reset them to see every account."
              : "There are no accounts yet."
          }
        />
      ) : (
        <>
          <Panel>
            <PanelTableWrap>
              <Table className="min-w-[820px]">
                <THead>
                  <TR>
                    <TH>Email</TH>
                    <TH>Plan</TH>
                    <TH>Status</TH>
                    <TH className="text-right">Scans</TH>
                    <TH>Last scan</TH>
                    <TH>Joined</TH>
                  </TR>
                </THead>
                <TBody>
                  {data.rows.map((row) => (
                    <TR key={row.user_id}>
                      <TD>
                        <div className="flex items-center gap-2">
                          <Link
                            href={`/admin/users/${row.user_id}`}
                            className="font-medium text-foreground underline-offset-4 hover:underline"
                          >
                            {row.email ?? row.user_id}
                          </Link>
                          {row.flagged ? (
                            <Badge
                              variant="outline"
                              className="border-severity-medium/40 bg-severity-medium/10 text-severity-medium"
                            >
                              Flagged
                            </Badge>
                          ) : null}
                        </div>
                      </TD>
                      <TD>
                        <span className="capitalize">{row.effective_tier}</span>
                        {/* Stored tier can outlive the paid period; effective is
                            what the product actually enforces, so show the drift
                            rather than only the flattering number. */}
                        {row.tier !== row.effective_tier ? (
                          <span className="ml-1.5 text-xs text-muted-foreground">stored: {row.tier}</span>
                        ) : null}
                      </TD>
                      <TD>
                        <StatusPill status={row.status} />
                      </TD>
                      <TD className="text-right tabular-nums text-muted-foreground">
                        {row.scans_this_period}
                      </TD>
                      <TD className="text-muted-foreground">
                        {row.last_scan_at ? formatDate(row.last_scan_at) : "—"}
                      </TD>
                      <TD className="text-muted-foreground">
                        {row.created_at ? formatDate(row.created_at) : "—"}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </PanelTableWrap>
          </Panel>

          <TablePagination
            page={data.page}
            pageCount={pageCount}
            total={data.total}
            itemNoun="account"
            onPageChange={setPage}
          />
        </>
      )}
    </>
  );
}
