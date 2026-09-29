"use client";

import { useState } from "react";
import { Loader2, Upload } from "lucide-react";

import { marketplaceAdminApi, type BulkPublishResult } from "@/entities/admin";
import { ApiError } from "@/shared/api";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";

/**
 * "Apply popularity bar": the one admin action that publishes many registry
 * drafts at once, and sets the published MCP servers below the same bar back
 * to draft (DECISIONS.md ADR-053, ADR-054).
 *
 * It always previews first. The dialog states the exact count, the criteria
 * as the server applied them, and why the rest stay drafts; only then can the
 * admin confirm. The server recomputes the set on publish rather than trusting
 * the preview, and each item still goes through the publish gate. Everything
 * happens inside the dialog, in a live region, so the result is announced
 * where the admin's focus already is.
 */

type Phase =
  | { kind: "previewing" }
  | { kind: "preview"; result: BulkPublishResult }
  | { kind: "publishing"; preview: BulkPublishResult }
  | { kind: "done"; result: BulkPublishResult }
  | { kind: "error"; message: string };

const n = (value: number) => value.toLocaleString();

const DEFAULT_MIN_STARS = 50;

/** A whole number of stars within the server's accepted range, or null. */
function parseStars(raw: string): number | null {
  const value = Number(raw);
  return Number.isInteger(value) && value >= 1 && value <= 1_000_000 ? value : null;
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function BulkPublishControl({ onPublished }: { onPublished: () => void }) {
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState<Phase>({ kind: "previewing" });
  const [starsInput, setStarsInput] = useState(String(DEFAULT_MIN_STARS));
  const minStars = parseStars(starsInput);

  async function startPreview(stars = minStars ?? DEFAULT_MIN_STARS) {
    setOpen(true);
    setStarsInput(String(stars));
    setPhase({ kind: "previewing" });
    try {
      setPhase({ kind: "preview", result: await marketplaceAdminApi.bulkPublishPreview(stars) });
    } catch (error) {
      setPhase({ kind: "error", message: errorText(error, "The preview could not be loaded.") });
    }
  }

  async function publish(preview: BulkPublishResult) {
    setPhase({ kind: "publishing", preview });
    try {
      // The bar the preview was computed at, not whatever the field holds
      // now: the confirm button names that preview's counts.
      const result = await marketplaceAdminApi.bulkPublish(preview.criteria.min_github_stars);
      setPhase({ kind: "done", result });
      onPublished();
    } catch (error) {
      setPhase({ kind: "error", message: errorText(
          error,
          "The request did not complete. Some changes may already be made; preview again to see what is left.",
        ) });
      onPublished();
    }
  }

  const busy = phase.kind === "previewing" || phase.kind === "publishing";

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => void startPreview()}>
        <Upload className="size-4" aria-hidden="true" />
        Apply popularity bar
      </Button>

      <Dialog open={open} onOpenChange={(next) => (!busy ? setOpen(next) : null)}>
        {/* Held inside the viewport, with the header and the actions always
            visible and only the body scrolling between them: Base UI's
            "inside scroll" dialog. The preview can list dozens of lines, and
            a dialog taller than the screen hid its own Publish button. */}
        <DialogContent
          className="max-h-[calc(100dvh-2rem)] max-w-lg grid-rows-[auto_minmax(0,1fr)_auto]"
          showCloseButton={!busy}
        >
          <DialogHeader>
            <DialogTitle>Apply popularity bar</DialogTitle>
            <DialogDescription>
              Publishes the registry drafts that meet the bar and sets published MCP servers below it back
              to draft. The registry sync keeps adding new servers as drafts.
            </DialogDescription>
            <form
              className="mt-2 flex flex-wrap items-end gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                if (minStars !== null) void startPreview(minStars);
              }}
            >
              <div className="grid gap-1">
                <Label htmlFor="bulk-min-stars">Minimum GitHub stars</Label>
                <Input
                  id="bulk-min-stars"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={1_000_000}
                  step={1}
                  className="w-32"
                  value={starsInput}
                  disabled={busy}
                  aria-invalid={minStars === null}
                  aria-describedby="bulk-min-stars-hint"
                  onChange={(event) => setStarsInput(event.target.value)}
                />
              </div>
              <Button type="submit" variant="outline" disabled={busy || minStars === null}>
                Preview
              </Button>
              <p id="bulk-min-stars-hint" className="basis-full text-xs text-muted-foreground">
                {minStars === null ? "Enter a whole number from 1 to 1,000,000." : "Change it and preview again to compare."}
              </p>
            </form>
          </DialogHeader>

          <div
            role="status"
            aria-live="polite"
            aria-busy={busy}
            tabIndex={0}
            aria-label="Preview"
            className="-mx-4 grid min-h-0 content-start gap-3 overflow-y-auto overscroll-contain px-4"
          >
            {phase.kind === "previewing" ? (
              <p className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                Checking which drafts qualify…
              </p>
            ) : null}
            {phase.kind === "publishing" ? (
              <p className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                Publishing {n(phase.preview.batch)} and unpublishing {n(phase.preview.below_bar)}…
              </p>
            ) : null}
            {phase.kind === "preview" ? <PreviewBody result={phase.result} /> : null}
            {phase.kind === "done" ? <DoneBody result={phase.result} /> : null}
            {phase.kind === "error" ? (
              <p className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-rose-700 dark:text-rose-300">
                <span className="font-medium">Not done: </span>
                {phase.message}
              </p>
            ) : null}
          </div>

          <DialogFooter>
            <Button variant="outline" disabled={busy} onClick={() => setOpen(false)}>
              {phase.kind === "preview" ? "Cancel" : "Close"}
            </Button>
            {phase.kind === "preview" && (phase.result.batch > 0 || phase.result.below_bar > 0) ? (
              <Button onClick={() => void publish(phase.result)}>{confirmLabel(phase.result)}</Button>
            ) : null}
            {phase.kind === "done" && phase.result.remaining > 0 ? (
              <Button onClick={() => void startPreview(phase.result.criteria.min_github_stars)}>
                Preview the next batch
              </Button>
            ) : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function confirmLabel(result: BulkPublishResult): string {
  const parts = [
    result.batch > 0 ? `publish ${n(result.batch)}` : null,
    result.below_bar > 0 ? `unpublish ${n(result.below_bar)}` : null,
  ].filter(Boolean);
  const text = parts.join(" and ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function Criteria({ result }: { result: BulkPublishResult }) {
  const c = result.criteria;
  return (
    <div>
      <p className="font-medium">A draft qualifies when it is:</p>
      <ul className="mt-1 list-disc space-y-0.5 ps-5 text-muted-foreground">
        <li>a public MCP server the registry sync added, still a draft;</li>
        <li>at {n(c.min_github_stars)} or more GitHub stars;</li>
        <li>complete enough to pass the publish gate (a title, a description, and something to install);</li>
        <li>
          the only listing for its repository: none if that repository is already published, otherwise the
          most-starred draft.
        </li>
      </ul>
      <p className="mt-1 text-muted-foreground">
        At most {n(c.max_per_call)} are published per run. A published MCP server known to have fewer than{" "}
        {n(c.min_github_stars)} stars goes back to draft; one whose stars are not known yet stays.
      </p>
    </div>
  );
}

function Skipped({ result }: { result: BulkPublishResult }) {
  const s = result.skipped;
  return (
    <div>
      <p className="font-medium">Staying drafts:</p>
      <ul className="mt-1 space-y-0.5 text-muted-foreground">
        <li>{n(s.already_published_repository)} whose repository is already published</li>
        <li>{n(s.failed_gate)} that fail the publish gate</li>
        <li>{n(s.duplicate_repository)} duplicates of a better-starred draft for the same repository</li>
      </ul>
      {result.gate_reasons.length > 0 ? (
        <>
          <p className="mt-2 font-medium">Most common gate refusals:</p>
          <ul className="mt-1 space-y-0.5 text-muted-foreground">
            {result.gate_reasons.map((r) => (
              <li key={r.reason}>
                <span className="tabular-nums">{n(r.count)}</span>: {r.reason}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

function SampleList({ label, items }: { label: string; items: BulkPublishResult["sample"] }) {
  return (
    <ul aria-label={label} className="mt-1 space-y-0.5 rounded-md border border-border px-3 py-2 text-muted-foreground">
      {items.map((item) => (
        <li key={item.id} className="flex justify-between gap-3">
          <span className="min-w-0 truncate">{item.title ?? item.slug}</span>
          <span className="shrink-0 tabular-nums">
            {item.github_stars != null ? `${n(item.github_stars)} stars` : "stars not known"}
          </span>
        </li>
      ))}
    </ul>
  );
}

function StarCounts({ result }: { result: BulkPublishResult }) {
  const unknown = result.star_counts.find((c) => c.min_stars === null);
  return (
    <div>
      <p className="font-medium">Drafts at each bar, before the publish check:</p>
      <table className="mt-1 w-full text-muted-foreground">
        <thead className="sr-only">
          <tr>
            <th scope="col">Minimum stars</th>
            <th scope="col">Drafts</th>
          </tr>
        </thead>
        <tbody>
          {result.star_counts
            .filter((c) => c.min_stars !== null)
            .map((c) => (
              <tr
                key={c.min_stars}
                className={c.min_stars === result.criteria.min_github_stars ? "font-medium text-foreground" : ""}
              >
                <td>{n(c.min_stars as number)}+ stars</td>
                <td className="text-right tabular-nums">{n(c.drafts)}</td>
              </tr>
            ))}
        </tbody>
      </table>
      {unknown && unknown.drafts > 0 ? (
        <p className="mt-1 text-xs text-muted-foreground">
          {n(unknown.drafts)} drafts have no star count yet: no GitHub repository, or not fetched yet. Stars are
          refreshed every hour.
        </p>
      ) : null}
    </div>
  );
}

function PreviewBody({ result }: { result: BulkPublishResult }) {
  const publishing =
    result.qualifying === 0
      ? "No drafts qualify right now."
      : `${n(result.batch)} drafts will be published${
          result.remaining > 0 ? ` now, of ${n(result.qualifying)} that qualify` : ""
        }.`;
  const unpublishing =
    result.below_bar > 0
      ? `${n(result.below_bar)} published servers are below the bar and will go back to draft.`
      : "No published server is below the bar.";
  return (
    <>
      <p className="text-base font-medium">
        {publishing} {unpublishing}
      </p>
      <StarCounts result={result} />
      <Criteria result={result} />
      <Skipped result={result} />
      {result.sample.length > 0 ? (
        <div>
          <p className="font-medium">To publish, first {n(result.sample.length)}, most popular first:</p>
          <SampleList label="Drafts that will be published" items={result.sample} />
        </div>
      ) : null}
      {result.below_bar_sample.length > 0 ? (
        <div>
          <p className="font-medium">
            Going back to draft
            {result.below_bar > result.below_bar_sample.length ? `, first ${n(result.below_bar_sample.length)}` : ""}:
          </p>
          <SampleList label="Published servers that will go back to draft" items={result.below_bar_sample} />
        </div>
      ) : null}
    </>
  );
}

function DoneBody({ result }: { result: BulkPublishResult }) {
  return (
    <>
      <p className="text-base font-medium">
        Published {n(result.published)}. Set back to draft {n(result.unpublished)}.
      </p>
      {result.failed.length > 0 ? (
        <div>
          <p className="font-medium text-rose-700 dark:text-rose-300">
            {n(result.failed.length)} could not be changed and keep their status:
          </p>
          <ul className="mt-1 space-y-0.5 text-muted-foreground">
            {result.failed.slice(0, 5).map((f) => (
              <li key={f.id}>
                {f.slug ?? f.id}: {f.reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {result.remaining > 0 ? (
        <p>{n(result.remaining)} more qualify. Preview the next batch to continue.</p>
      ) : (
        <p className="text-muted-foreground">No qualifying drafts are left.</p>
      )}
    </>
  );
}
