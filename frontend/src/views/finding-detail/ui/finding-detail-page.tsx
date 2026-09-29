"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, CheckCircle2, Flag, RotateCcw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { ApiError } from "@/shared/api";
import { findingApi } from "@/entities/finding";
import type { Finding } from "@/entities/finding";
import { OWASP_CATEGORY_LABELS, SEVERITY_MEANINGS, TRIAGE_LABELS } from "@/entities/finding";
import { PageHeader, SectionCard, TechnicalDetails } from "@/shared/ui";
import { SeverityBadge } from "@/entities/finding";
import { Button } from "@/shared/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Skeleton } from "@/shared/ui/skeleton";
import { Textarea } from "@/shared/ui/textarea";
import { riskImpactForSeverity } from "@/entities/finding";
import { formatDateTime } from "@/shared/lib/format";
import { ExplainButton } from "@/features/ai-explain";
import { WORKSPACE_PERMISSIONS, useWorkspacePermission } from "@/entities/organization";

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
  const triage = useWorkspacePermission(WORKSPACE_PERMISSIONS.findingsTriage);

  useEffect(() => {
    findingApi
      .getFinding(findingId)
      .then((loadedFinding) => {
        setFinding(loadedFinding);
        setTriageReason(loadedFinding.triage_reason ?? "");
      })
      .catch((err) => {
        const message = err instanceof ApiError ? err.message : "We could not load this problem.";
        setError(message);
      });
  }, [findingId]);

  async function updateStatus(status: "open" | "fixed" | "false_positive", reason?: string) {
    setTriaging(true);
    try {
      const updated = await findingApi.triageFinding(findingId, status, reason);
      setFinding(updated);
      setTriageReason(updated.triage_reason ?? "");
      toast.success(status === "open" ? "Marked as not fixed" : status === "fixed" ? "Marked as fixed" : "Saved as not a real problem");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "We could not update this problem.");
    } finally {
      setTriaging(false);
    }
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="size-4" />
        <AlertTitle>We could not load this problem</AlertTitle>
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
      : "No file, line or manifest field was recorded for this problem.";

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
        Back to the scan
      </Link>

      <PageHeader
        pretitle="Problem found"
        title={finding.title}
        description="What is wrong, why it matters and what to do about it. The exact scanner data is under Technical details."
        actions={
          triage.allowed ? (
          <>
              {finding.triage_status === "open" ? (
                <Button variant="outline" disabled={triaging} onClick={() => void updateStatus("fixed")}>
                  <CheckCircle2 className="size-4" />
                  Mark as fixed
                </Button>
              ) : (
                <Button variant="outline" disabled={triaging} onClick={() => void updateStatus("open")}>
                  <RotateCcw className="size-4" />
                  Mark as not fixed
                </Button>
              )}
          </>
          ) : undefined
        }
      />

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.3fr)_360px]">
        {/* Simple first, technical second. The four answers come from the
            rule catalogue (the same entry as the technical impact and fix),
            so they restate the scanner's result rather than add to it. A
            finding with no known rule falls back to the scanner's own text. */}
        <SectionCard
          title="The problem"
          description="From Aevrin's scan. Nothing here was written by AI."
        >
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={finding.severity} />
              <span className="text-sm text-muted-foreground">{SEVERITY_MEANINGS[finding.severity]}</span>
            </div>

            <SectionBody title="What is wrong?" body={finding.plain?.problem ?? finding.description} />
            {finding.plain?.why ?? finding.impact ? (
              <SectionBody title="Why does it matter?" body={(finding.plain?.why ?? finding.impact) as string} />
            ) : null}
            {finding.plain ? <SectionBody title="What could happen?" body={finding.plain.could_happen} /> : null}
            <SectionBody title="What should I do?" body={finding.plain?.fix ?? finding.remediation} />

            <AiReview finding={finding} />
            <ExplainButton subjectType="finding" subjectId={findingId} label="Explain this problem with AI" />

            <div className="rounded-xl border border-border bg-background/80 p-4">
              <TechnicalDetails>
                <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-[10rem_minmax(0,1fr)]">
                  <TechRow label="Finding" value={finding.title} />
                  <TechRow label="Severity" value={finding.severity} />
                  <TechRow label="Rule" value={finding.rule_id ?? "None recorded"} mono />
                  <TechRow
                    label="Category"
                    value={`${finding.owasp_category}: ${OWASP_CATEGORY_LABELS[finding.owasp_category] ?? "Unknown category"}`}
                  />
                  <TechRow label="Scanner" value={finding.tool} mono />
                  <TechRow label="Location" value={location} mono />
                  {finding.additional_locations.length > 0 ? (
                    <TechRow
                      label="Other locations"
                      value={finding.additional_locations
                        .map((extra) => extra.file_path ?? extra.manifest_field ?? "unknown")
                        .join(", ")}
                      mono
                    />
                  ) : null}
                  {finding.affected_tools.length > 0 ? (
                    <TechRow label="Tools with the problem" value={finding.affected_tools.join(", ")} mono />
                  ) : null}
                  {finding.evidence.length > 0 ? (
                    <TechRow label="What we found" value={finding.evidence.join("\n")} mono />
                  ) : null}
                  <TechRow label="Description" value={finding.description} />
                  {finding.impact ? <TechRow label="Impact" value={finding.impact} /> : null}
                  <TechRow label="Remediation" value={finding.remediation} />
                  <TechRow label="Risk score impact" value={riskImpactForSeverity(finding.severity)} />
                  <TechRow label="Recorded" value={formatDateTime(finding.created_at)} />
                </dl>
              </TechnicalDetails>
            </div>
          </div>
        </SectionCard>

        <div className="space-y-6">
          <SectionCard title="Status" description="Every change is saved with its reason and time.">
            <div className="space-y-4 text-sm leading-6 text-muted-foreground">
              <p>Right now: <strong className="text-foreground">{TRIAGE_LABELS[finding.triage_status]}</strong></p>
              {finding.triaged_at ? (
                <div className="rounded-xl border border-border bg-background/80 p-4">
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Last changed</p>
                  <p className="mt-2 text-foreground">{formatDateTime(finding.triaged_at)}</p>
                  {finding.triage_reason ? <p className="mt-2 whitespace-pre-wrap">{finding.triage_reason}</p> : null}
                </div>
              ) : null}

              {triage.allowed ? (
              <div className="space-y-3 border-t border-border pt-4">
                  <div>
                    <label htmlFor="false-positive-reason" className="font-medium text-foreground">Not a real problem? Say why</label>
                    <p className="mt-1 text-xs">If this does not apply to you or cannot be used against you (a &ldquo;false positive&rdquo;), explain why. A reason is required, and it is saved with the report.</p>
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
                      {finding.triage_status === "false_positive" ? "Update the reason" : "Mark as not a real problem"}
                    </Button>
                  </div>
              </div>
              ) : (
                <p className="border-t border-border pt-4">
                  Your workspace role ({triage.role}) does not include &ldquo;Triage findings&rdquo;, so
                  you cannot change this problem&apos;s status.
                </p>
              )}
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
  confirmed: { label: "Agrees this is a real problem", className: "text-severity-high" },
  likely_false_positive: { label: "Thinks this may not be a real problem", className: "text-chart-1" },
  needs_review: { label: "Could not decide", className: "text-muted-foreground" },
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
        <p className="text-sm font-medium text-foreground">AI second opinion</p>
        <span className={`text-sm font-medium ${verdict.className}`}>{verdict.label}</span>
        {/* Only shown when the model disagrees with the scanner. An identical
            severity repeated back adds nothing and reads as noise. */}
        {finding.llm_severity && finding.llm_severity !== finding.severity ? (
          <span className="text-xs text-muted-foreground">
            suggests {finding.llm_severity} instead of {finding.severity}
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
        A second opinion, not a replacement for the scan. The score is worked out from the
        scanner&apos;s severity, never from this.
      </p>
    </div>
  );
}

function TechRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <>
      <dt className="font-medium text-foreground">{label}</dt>
      <dd className={`whitespace-pre-wrap break-words ${mono ? "font-mono" : ""}`}>{value}</dd>
    </>
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
