"use client";

import { CheckCircle2, CircleDashed, GitPullRequest, Loader2, XCircle } from "lucide-react";
import type { Finding } from "@/lib/types";
import { Button } from "@/components/ui/button";

/**
 * Live progress for a whole-scan Fix It run.
 *
 * Modelled on the scan stage list rather than a bare spinner, because a
 * single fix takes tens of seconds (a model call, a clone, a scanner re-run,
 * then GitHub) and a run of several takes minutes. A spinner over that long
 * is indistinguishable from a hang.
 *
 * State comes from the findings the page already polls, so this window is a
 * view of real per-finding status and never a separate animation guessing at
 * what the backend is doing.
 */

const STEP_LABEL: Record<string, string> = {
  queued: "Waiting",
  in_progress: "Drafting patch, re-running the scanner, opening a PR",
  fixed: "Pull request opened",
  failed: "Couldn't be fixed automatically",
};

function StatusIcon({ status }: { status: string }) {
  if (status === "fixed") return <CheckCircle2 className="size-4 shrink-0 text-chart-1" />;
  if (status === "failed") return <XCircle className="size-4 shrink-0 text-severity-high" />;
  if (status === "in_progress") return <Loader2 className="size-4 shrink-0 animate-spin text-brand-text" />;
  return <CircleDashed className="size-4 shrink-0 text-muted-foreground" />;
}

export function FixProgressDialog({
  findings,
  onCancel,
  onClose,
  cancelling,
}: {
  findings: Finding[];
  onCancel: () => void;
  onClose: () => void;
  cancelling: boolean;
}) {
  const tracked = findings.filter((f) =>
    ["queued", "in_progress", "fixed", "failed"].includes(f.autofix_status),
  );
  if (tracked.length === 0) return null;

  const done = tracked.filter((f) => f.autofix_status === "fixed" || f.autofix_status === "failed").length;
  const fixed = tracked.filter((f) => f.autofix_status === "fixed").length;
  const failed = tracked.filter((f) => f.autofix_status === "failed").length;
  const running = done < tracked.length;
  const pct = Math.round((done / tracked.length) * 100);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Fix It progress"
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
    >
      <div className="absolute inset-0 bg-black/60" onClick={running ? undefined : onClose} aria-hidden="true" />

      <div className="relative w-full max-w-lg overflow-hidden rounded-xl border border-border bg-card shadow-2xl">
        <div className="border-b border-border px-5 py-4">
          <h2 className="flex items-center gap-2 text-sm font-medium">
            {running ? (
              <Loader2 className="size-4 animate-spin text-brand-text" />
            ) : (
              <GitPullRequest className="size-4 text-chart-1" />
            )}
            {running ? "Fixing findings" : "Fix run finished"}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {running
              ? `${done} of ${tracked.length} done. One pull request per finding, each re-verified by the scanner that raised it before it opens.`
              : `${fixed} fixed${failed ? `, ${failed} couldn't be fixed automatically` : ""}.`}
          </p>

          <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-brand transition-[width] duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        <ul className="max-h-80 divide-y divide-border overflow-y-auto">
          {tracked.map((f) => (
            <li key={f.id} className="flex items-start gap-3 px-5 py-3">
              <span className="mt-0.5">
                <StatusIcon status={f.autofix_status} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] text-foreground">{f.title}</span>
                {/* The file path is the only thing distinguishing two
                    findings that share a title, so it is never dropped. */}
                {f.file_path ? (
                  <span className="mt-0.5 block truncate font-mono text-[11px] text-muted-foreground">
                    {f.file_path}
                  </span>
                ) : null}
                <span className="mt-0.5 block text-[11px] text-muted-foreground">
                  {f.autofix_status === "failed" && f.autofix_failure_reason
                    ? f.autofix_failure_reason
                    : STEP_LABEL[f.autofix_status]}
                </span>
              </span>
              {f.autofix_status === "fixed" && f.autofix_pr_url ? (
                <a
                  href={f.autofix_pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 text-[11px] text-brand-text hover:underline"
                >
                  View PR
                </a>
              ) : null}
            </li>
          ))}
        </ul>

        <div className="flex items-center justify-between gap-3 border-t border-border px-5 py-3">
          <p className="text-[11px] text-muted-foreground">
            {running
              ? "Cancelling stops the queue; the fix in flight finishes first."
              : "You can close this window."}
          </p>
          {running ? (
            <Button variant="outline" size="sm" disabled={cancelling} onClick={onCancel}>
              {cancelling ? "Cancelling…" : "Cancel"}
            </Button>
          ) : (
            <Button size="sm" onClick={onClose}>
              Done
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
