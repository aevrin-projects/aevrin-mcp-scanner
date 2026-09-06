"use client";

import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { Button } from "./button";

/**
 * The pagination bar under a paged table.
 *
 * Shared because three admin tables page the same way and had drifted into
 * three slightly different footers - one showed "Page 2 of 7", one showed
 * nothing until there were two pages, one showed only Next/Previous.
 *
 * First/last are here rather than just next/previous because the thing an
 * admin most often wants from a paged list is the other end of it, and
 * getting there by pressing Next repeatedly is not navigation.
 */
export function TablePagination({
  page,
  pageCount,
  total,
  itemNoun = "row",
  onPageChange,
  className,
}: {
  page: number;
  pageCount: number;
  total?: number;
  /** Singular; pluralised with a trailing "s". */
  itemNoun?: string;
  onPageChange: (page: number) => void;
  className?: string;
}) {
  const atStart = page <= 1;
  const atEnd = page >= pageCount;

  return (
    <div
      className={cn(
        "flex flex-col gap-3 px-1 sm:flex-row sm:items-center sm:justify-between",
        className,
      )}
    >
      <p className="text-sm text-muted-foreground" aria-live="polite">
        {total === undefined
          ? `Page ${page} of ${pageCount}`
          : `${total.toLocaleString()} ${itemNoun}${total === 1 ? "" : "s"} · page ${page} of ${pageCount}`}
      </p>
      <div className="flex items-center gap-1.5">
        <Button
          variant="outline"
          size="sm"
          className="hidden size-8 p-0 sm:inline-flex"
          disabled={atStart}
          onClick={() => onPageChange(1)}
          aria-label="Go to first page"
        >
          <ChevronsLeft className="size-4" />
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={atStart}
          onClick={() => onPageChange(page - 1)}
          aria-label="Go to previous page"
        >
          <ChevronLeft className="size-4" />
          <span className="hidden sm:inline">Previous</span>
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={atEnd}
          onClick={() => onPageChange(page + 1)}
          aria-label="Go to next page"
        >
          <span className="hidden sm:inline">Next</span>
          <ChevronRight className="size-4" />
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="hidden size-8 p-0 sm:inline-flex"
          disabled={atEnd}
          onClick={() => onPageChange(pageCount)}
          aria-label="Go to last page"
        >
          <ChevronsRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}
