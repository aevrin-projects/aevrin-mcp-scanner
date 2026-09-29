"use client";

import { useState } from "react";
import { Loader2, Upload } from "lucide-react";

import { marketplaceAdminApi, type BulkPublishResult } from "@/entities/admin";
import { ApiError } from "@/shared/api";
import { Button } from "@/shared/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";

/**
 * "Publish qualifying drafts": the one admin action that publishes many
 * registry drafts at once (DECISIONS.md ADR-053).
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

function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export function BulkPublishControl({ onPublished }: { onPublished: () => void }) {
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState<Phase>({ kind: "previewing" });

  async function startPreview() {
    setOpen(true);
    setPhase({ kind: "previewing" });
    try {
      setPhase({ kind: "preview", result: await marketplaceAdminApi.bulkPublishPreview() });
    } catch (error) {
      setPhase({ kind: "error", message: errorText(error, "The preview could not be loaded.") });
    }
  }

  async function publish(preview: BulkPublishResult) {
    setPhase({ kind: "publishing", preview });
    try {
      const result = await marketplaceAdminApi.bulkPublish();
      setPhase({ kind: "done", result });
      onPublished();
    } catch (error) {
      setPhase({ kind: "error", message: errorText(
          error,
          "The request did not complete. Some drafts may already be published; preview again to see what is left.",
        ) });
      onPublished();
    }
  }

  const busy = phase.kind === "previewing" || phase.kind === "publishing";

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => void startPreview()}>
        <Upload className="size-4" aria-hidden="true" />
        Publish qualifying drafts
      </Button>

      <Dialog open={open} onOpenChange={(next) => (!busy ? setOpen(next) : null)}>
        <DialogContent className="max-w-lg" showCloseButton={!busy}>
          <DialogHeader>
            <DialogTitle>Publish qualifying drafts</DialogTitle>
            <DialogDescription>
              Publishes the registry drafts that meet the quality bar. Everything else stays a draft,
              and the registry sync keeps adding new servers as drafts.
            </DialogDescription>
          </DialogHeader>

          <div role="status" aria-live="polite" aria-busy={busy} className="grid gap-3">
            {phase.kind === "previewing" ? (
              <p className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                Checking which drafts qualify…
              </p>
            ) : null}
            {phase.kind === "publishing" ? (
              <p className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                Publishing {n(phase.preview.batch)} drafts…
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
            {phase.kind === "preview" && phase.result.batch > 0 ? (
              <Button onClick={() => void publish(phase.result)}>
                Publish {n(phase.result.batch)}
              </Button>
            ) : null}
            {phase.kind === "done" && phase.result.remaining > 0 ? (
              <Button onClick={() => void startPreview()}>Preview the next batch</Button>
            ) : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function Criteria({ result }: { result: BulkPublishResult }) {
  const c = result.criteria;
  return (
    <div>
      <p className="font-medium">A draft qualifies when it is:</p>
      <ul className="mt-1 list-disc space-y-0.5 ps-5 text-muted-foreground">
        <li>a public MCP server the registry sync added, still a draft;</li>
        <li>
          at {n(c.min_github_stars)} or more GitHub stars, or {n(c.min_npm_downloads_last_month)} or more npm
          downloads last month;
        </li>
        <li>complete enough to pass the publish gate (a title, a description, and something to install);</li>
        <li>
          the only listing for its repository: none if that repository is already published, otherwise the
          most-starred draft.
        </li>
      </ul>
      <p className="mt-1 text-muted-foreground">At most {n(c.max_per_call)} are published per run.</p>
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

function PreviewBody({ result }: { result: BulkPublishResult }) {
  if (result.qualifying === 0) {
    return (
      <>
        <p className="font-medium">No drafts qualify right now.</p>
        <Criteria result={result} />
        <Skipped result={result} />
      </>
    );
  }
  return (
    <>
      <p className="text-base font-medium">
        {n(result.batch)} drafts will be published
        {result.remaining > 0 ? ` now, of ${n(result.qualifying)} that qualify` : ""}.
      </p>
      <Criteria result={result} />
      <Skipped result={result} />
      {result.sample.length > 0 ? (
        <div>
          <p className="font-medium">First {n(result.sample.length)}, most popular first:</p>
          <ul
            tabIndex={0}
            aria-label="Drafts that will be published"
            className="mt-1 max-h-40 space-y-0.5 overflow-y-auto rounded-md border border-border px-3 py-2 text-muted-foreground"
          >
            {result.sample.map((item) => (
              <li key={item.id} className="flex justify-between gap-3">
                <span className="truncate">{item.title ?? item.slug}</span>
                <span className="shrink-0 tabular-nums">
                  {item.github_stars != null ? `${n(item.github_stars)} stars` : `${n(item.npm_downloads_last_month ?? 0)} npm`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}

function DoneBody({ result }: { result: BulkPublishResult }) {
  return (
    <>
      <p className="text-base font-medium">Published {n(result.published)}.</p>
      {result.failed.length > 0 ? (
        <div>
          <p className="font-medium text-rose-700 dark:text-rose-300">
            {n(result.failed.length)} could not be published and stay drafts:
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
