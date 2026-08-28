"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle2, Loader2 } from "lucide-react";

import { listMySubmissions, submitServer, type Submission } from "@/entities/marketplace";
import { ApiError } from "@/shared/api";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Textarea } from "@/shared/ui/textarea";
import { EmptyState, PageHeader, Panel, PanelBody, PanelHeader, PanelTitle } from "@/shared/ui";

/**
 * Submitting a server.
 *
 * One field, plus an optional note. Everything else — name, description,
 * licence, stars, README, packaging — is read from the source by Aevrin. A
 * form that asked a submitter to type metadata would be a form that lets
 * someone write whatever they like about software they do not own.
 *
 * The copy is explicit that nothing is published without a scan, because a
 * submitter who expects instant publication and gets a review queue will
 * assume something is broken.
 */

export function SubmitPage() {
  const [url, setUrl] = useState("");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [submissions, setSubmissions] = useState<Submission[]>([]);

  useEffect(() => {
    listMySubmissions()
      .then(setSubmissions)
      .catch(() => setSubmissions([]));
  }, [submitted]);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      await submitServer(url.trim(), note.trim() || undefined);
      setSubmitted(true);
      setUrl("");
      setNote("");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The submission could not be sent. Try again shortly.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Submit an MCP server"
        description="Paste a repository or server URL. Aevrin reads the rest from the source."
      />

      <Panel>
        <PanelHeader>
          <PanelTitle>What happens next</PanelTitle>
        </PanelHeader>
        <PanelBody>
          <ol className="space-y-3 text-sm text-muted-foreground">
            <li>1. Aevrin fetches the source and derives the metadata.</li>
            <li>2. The server is scanned: code security, MCP surface, dependencies.</li>
            <li>3. An administrator reviews the result.</li>
            <li>
              4. If approved, it is published with its grade.{" "}
              <span className="text-foreground">
                Nothing is published without a scan.
              </span>
            </li>
          </ol>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader>
          <PanelTitle>Server URL</PanelTitle>
        </PanelHeader>
        <PanelBody className="space-y-8 py-6">
          {submitted ? (
            <div className="flex items-start gap-3 rounded-lg border border-severity-low/25 bg-severity-low/10 p-4">
              <CheckCircle2
                className="mt-0.5 size-4 shrink-0 text-severity-low"
                aria-hidden="true"
              />
              <div>
                <p className="text-sm font-medium">Submission received</p>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  It is queued for scanning and review. You can track it below.
                </p>
              </div>
            </div>
          ) : null}

          <label className="block space-y-2.5 text-sm">
            <span className="font-medium">Repository or MCP server URL</span>
            <Input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://github.com/owner/repo"
              type="url"
              className="h-10"
            />
            <span className="block text-xs leading-relaxed text-muted-foreground">
              A public GitHub repository, or a public HTTPS MCP endpoint. Private
              and internal addresses are refused.
            </span>
          </label>

          <label className="block space-y-2.5 text-sm">
            <span className="font-medium">Anything a reviewer should know (optional)</span>
            <Textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={4}
              maxLength={2000}
              placeholder="e.g. this is the official server for our API"
            />
          </label>

          {error ? <p className="text-sm text-severity-critical">{error}</p> : null}

          <div className="flex items-center gap-3 border-t border-border pt-6">
            <Button
              onClick={() => void submit()}
              disabled={submitting || !url.trim().startsWith("https://")}
              size="lg"
            >
              {submitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  Submitting
                </>
              ) : (
                "Submit for review"
              )}
            </Button>
            <span className="text-xs text-muted-foreground">
              Only the URL is required. Everything else is read from the source.
            </span>
          </div>
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader>
          <PanelTitle>Your submissions</PanelTitle>
        </PanelHeader>
        <PanelBody>
          {submissions.length === 0 ? (
            <EmptyState
              title="No submissions yet"
              body="Servers you submit will appear here with their review status."
            />
          ) : (
            <div className="space-y-2">
              {submissions.map((submission) => (
                <div
                  key={submission.id}
                  className="flex items-start justify-between gap-4 rounded-md border border-border p-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {submission.listing?.title ?? submission.sourceUrl}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {submission.sourceUrl}
                    </p>
                    {submission.reviewReason ? (
                      <p className="mt-1 text-xs text-muted-foreground">
                        {submission.reviewReason}
                      </p>
                    ) : null}
                  </div>
                  <div className="shrink-0 text-right">
                    <StatusPill status={submission.status} />
                    {submission.status === "published" && submission.listing ? (
                      <Link
                        href={`/marketplace/${submission.listing.slug}`}
                        className="mt-1 block text-xs hover:underline"
                      >
                        View listing
                      </Link>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </PanelBody>
      </Panel>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const style =
    status === "published"
      ? "border-severity-low/25 bg-severity-low/10 text-severity-low"
      : status === "rejected"
        ? "border-severity-critical/25 bg-severity-critical/10 text-severity-critical"
        : "border-border bg-muted text-muted-foreground";

  const label =
    {
      review: "In review",
      scanning: "Scanning",
      published: "Published",
      rejected: "Not accepted",
      approved: "Approved",
      submitted: "Submitted",
      draft: "Draft",
    }[status] ?? status;

  return (
    <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${style}`}>
      {label}
    </span>
  );
}
