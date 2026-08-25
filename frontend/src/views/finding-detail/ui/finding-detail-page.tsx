"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, CheckCircle2, Flag, RotateCcw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { ApiError } from "@/shared/api";
import { findingApi } from "@/entities/finding";
import type { Finding } from "@/entities/finding";
import { OWASP_CATEGORY_LABELS } from "@/entities/finding";
import { PageHeader, SectionCard } from "@/shared/ui";
import { SeverityBadge } from "@/entities/finding";
import { Button } from "@/shared/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Skeleton } from "@/shared/ui/skeleton";
import { Textarea } from "@/shared/ui/textarea";
import { scoreImpactForSeverity } from "@/entities/finding";
import { formatDateTime } from "@/shared/lib/format";

export function FindingDetailClient({
  scanId,
  findingId,
  returnTo,
}: {
  scanId: string;
  findingId: string;
  returnTo?: string;
}) {
  const [finding, setFinding] = useState<Finding | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [triaging, setTriaging] = useState(false);
  const [triageReason, setTriageReason] = useState("");

  useEffect(() => {
    findingApi
      .getFinding(findingId)
      .then((loadedFinding) => {
        setFinding(loadedFinding);
        setTriageReason(loadedFinding.triage_reason ?? "");
      })
      .catch((err) => {
        const message = err instanceof ApiError ? err.message : "Could not load this finding.";
        setError(message);
      });
  }, [findingId]);

  async function updateStatus(status: "open" | "fixed" | "false_positive", reason?: string) {
    setTriaging(true);
    try {
      const updated = await findingApi.triageFinding(findingId, status, reason);
      setFinding(updated);
      setTriageReason(updated.triage_reason ?? "");
      toast.success(status === "open" ? "Finding reopened" : status === "fixed" ? "Marked as fixed" : "False positive recorded");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not update this finding.");
    } finally {
      setTriaging(false);
    }
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="size-4" />
        <AlertTitle>Could not load finding</AlertTitle>
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  if (!finding) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-20 rounded-xl" />
        <Skeleton className="h-80 rounded-xl" />
      </div>
    );
  }

  const location = finding.file_path
    ? `${finding.file_path}${finding.line_start ? `:${finding.line_start}` : ""}`
    : finding.manifest_field
      ? `${finding.tool_name_in_manifest ? `${finding.tool_name_in_manifest} -> ` : ""}${finding.manifest_field}`
      : "No file, line, or manifest field was recorded for this finding.";

  const scanHref = `/scans/${scanId}`;
  // Search params are already decoded by Next.js. Keep navigation on this
  // scan instead of accepting an arbitrary client-supplied URL.
  const backHref = returnTo === scanHref || returnTo?.startsWith(`${scanHref}?`) ? returnTo : scanHref;

  return (
    <div className="space-y-6">
      <Link
        href={backHref}
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Back to filtered results
      </Link>

      <PageHeader
        pretitle="Finding"
        title={finding.title}
        description="Review the recorded severity, category, source, context, remediation, and auditable triage history."
        actions={
          !finding.not_tested ? (
            <>
              {finding.triage_status === "open" ? (
                <Button variant="outline" disabled={triaging} onClick={() => void updateStatus("fixed")}>
                  <CheckCircle2 className="size-4" />
                  Mark as fixed
                </Button>
              ) : (
                <Button variant="outline" disabled={triaging} onClick={() => void updateStatus("open")}>
                  <RotateCcw className="size-4" />
                  Reopen finding
                </Button>
              )}
            </>
          ) : null
        }
      />

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.3fr)_360px]">
        <SectionCard
          title="Finding context"
          description="Everything shown below comes from the stored finding record for this scan."
        >
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={finding.severity} />
              {finding.in_kev ? (
                <span className="rounded-full border border-red-500/40 bg-red-500/10 px-2 py-1 text-xs font-medium text-red-600 dark:text-red-400">
                  CISA KEV: confirmed exploited in the wild
                </span>
              ) : null}
              {finding.epss_score !== null ? (
                <span className="rounded-full border border-border px-2 py-1 text-xs text-muted-foreground">
                  EPSS {(finding.epss_score * 100).toFixed(finding.epss_score < 0.01 ? 2 : 0)}% exploitation probability (30d)
                </span>
              ) : null}
              <span className="rounded-full border border-border px-2 py-1 text-xs text-muted-foreground">
                {finding.triage_status.replace("_", " ")}
              </span>
              <span className="rounded-full border border-border px-2 py-1 text-xs text-muted-foreground">
                {OWASP_CATEGORY_LABELS[finding.owasp_category] ?? finding.owasp_category}
              </span>
              {finding.excluded_path ? (
                <span className="rounded-full border border-border px-2 py-1 text-xs text-muted-foreground">
                  Test/fixture path: excluded from score
                </span>
              ) : null}
            </div>
            {finding.original_severity && finding.original_severity !== finding.severity ? (
              <p className="text-xs text-muted-foreground">
                Downgraded from {finding.original_severity} based on {finding.in_kev ? "corroboration" : "low exploitation likelihood or scope"}: the tool&apos;s original severity is preserved here for audit.
              </p>
            ) : null}

            <div className="rounded-xl border border-border bg-background/80 p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Location</p>
              <p className="mt-2 break-all font-mono text-sm text-foreground">{location}</p>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <MetaPanel label="Scanner source" value={finding.tool} />
              <MetaPanel label="Recorded at" value={formatDateTime(finding.created_at)} />
              <MetaPanel label="Score impact" value={scoreImpactForSeverity(finding.severity)} />
              <MetaPanel label="Identifiers" value="Not available in the current backend response" />
            </div>

            <SectionBody title="Why it matters" body={finding.description} />
            <SectionBody title="Remediation" body={finding.remediation} />
            <AiReview finding={finding} />
          </div>
        </SectionCard>

        <div className="space-y-6">
          {finding.not_tested ? (
            <Alert>
              <AlertTriangle className="size-4" />
              <AlertTitle>Documented limitation</AlertTitle>
              <AlertDescription>
                This entry records a coverage limitation rather than an exploitable code finding, so remediation means performing the missing validation outside this static scan.
              </AlertDescription>
            </Alert>
          ) : null}

          <SectionCard title="Status" description="Triage changes are retained with their reason and timestamp.">
            <div className="space-y-4 text-sm leading-6 text-muted-foreground">
              <p>Current status: <strong className="text-foreground">{finding.triage_status.replace("_", " ")}</strong></p>
              {finding.triaged_at ? (
                <div className="rounded-xl border border-border bg-background/80 p-4">
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Last triage</p>
                  <p className="mt-2 text-foreground">{formatDateTime(finding.triaged_at)}</p>
                  {finding.triage_reason ? <p className="mt-2 whitespace-pre-wrap">{finding.triage_reason}</p> : null}
                </div>
              ) : null}

              {!finding.not_tested ? (
                <div className="space-y-3 border-t border-border pt-4">
                  <div>
                    <label htmlFor="false-positive-reason" className="font-medium text-foreground">False-positive reason</label>
                    <p className="mt-1 text-xs">Explain why this result is not applicable or not exploitable. The reason is required and stored with the report.</p>
                  </div>
                  <Textarea
                    id="false-positive-reason"
                    value={triageReason}
                    onChange={(event) => setTriageReason(event.target.value)}
                    maxLength={1000}
                    rows={5}
                    placeholder="Example: This credential pattern is generated test data and cannot authenticate against any environment."
                  />
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <span className="text-xs">{triageReason.length} / 1000</span>
                    <Button
                      variant="outline"
                      disabled={triaging || triageReason.trim().length < 3}
                      onClick={() => void updateStatus("false_positive", triageReason.trim())}
                    >
                      <Flag className="size-4" />
                      {finding.triage_status === "false_positive" ? "Update report" : "Report false positive"}
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}

/**
 * The AI second opinion on a scanner result.
 *
 * Deliberately rendered *below* the scanner's own description and
 * remediation, never in place of them. The deterministic result is what the
 * score is computed from; this is commentary on it. Presenting the two as
 * equals, or letting this one appear first, would imply the model can
 * overrule a scanner, which it cannot.
 */
const AI_CLASSIFICATION: Record<string, { label: string; className: string }> = {
  confirmed: { label: "Confirmed", className: "text-severity-high" },
  likely_false_positive: { label: "Likely false positive", className: "text-chart-1" },
  needs_review: { label: "Needs review", className: "text-muted-foreground" },
};

function AiReview({ finding }: { finding: Finding }) {
  if (!finding.llm_classification || !finding.llm_reasoning) return null;
  const verdict = AI_CLASSIFICATION[finding.llm_classification] ?? {
    label: finding.llm_classification.replace(/_/g, " "),
    className: "text-muted-foreground",
  };

  return (
    <div className="rounded-xl border border-brand/30 bg-brand/[0.04] p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Sparkles className="size-4 text-brand-text" />
        <p className="text-sm font-medium text-foreground">AI review</p>
        <span className={`text-sm font-medium ${verdict.className}`}>{verdict.label}</span>
        {/* Only shown when the model disagrees with the scanner. An identical
            severity repeated back adds nothing and reads as noise. */}
        {finding.llm_severity && finding.llm_severity !== finding.severity ? (
          <span className="text-xs text-muted-foreground">
            suggests {finding.llm_severity} rather than {finding.severity}
          </span>
        ) : null}
      </div>

      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
        {finding.llm_reasoning}
      </p>

      {finding.llm_remediation ? (
        <p className="mt-3 whitespace-pre-wrap border-t border-brand/20 pt-3 text-sm leading-6 text-muted-foreground">
          <span className="font-medium text-foreground">Suggested fix: </span>
          {finding.llm_remediation}
        </p>
      ) : null}

      {/* The model identifier is stored on the finding for auditability but
          deliberately not rendered, which vendor is behind this is an
          implementation detail, and naming it invites users to weigh the
          verdict by brand rather than by the reasoning shown above. */}
      <p className="mt-3 text-xs text-muted-foreground">
        A second opinion on the scanner result, not a replacement for it. The score above is
        computed from the scanner&apos;s severity, never from this.
      </p>
    </div>
  );
}

function MetaPanel({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-background/80 p-4">
      <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <p className="mt-2 text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

function SectionBody({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-xl border border-border bg-background/80 p-4">
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{body}</p>
    </div>
  );
}
