"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { Finding } from "@/lib/types";
import { OWASP_CATEGORY_LABELS } from "@/lib/types";
import { PageHeader, SectionCard } from "@/components/product-ui";
import { SeverityBadge } from "@/components/severity-badge";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { scoreImpactForSeverity, formatDateTime } from "@/lib/presentation";

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

  useEffect(() => {
    api
      .getFinding(findingId)
      .then(setFinding)
      .catch((err) => {
        const message = err instanceof ApiError ? err.message : "Could not load this finding.";
        setError(message);
      });
  }, [findingId]);

  async function markFixed() {
    setTriaging(true);
    try {
      const updated = await api.triageFinding(findingId, "fixed");
      setFinding(updated);
      toast.success("Marked as fixed");
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
        <Skeleton className="h-20 rounded-3xl" />
        <Skeleton className="h-80 rounded-3xl" />
      </div>
    );
  }

  const location = finding.file_path
    ? `${finding.file_path}${finding.line_start ? `:${finding.line_start}` : ""}`
    : finding.manifest_field
      ? `${finding.tool_name_in_manifest ? `${finding.tool_name_in_manifest} -> ` : ""}${finding.manifest_field}`
      : "No file, line, or manifest field was recorded for this finding.";

  const backHref = returnTo ? decodeURIComponent(returnTo) : `/scans/${scanId}`;

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
        title={finding.title}
        description="Review the recorded severity, category, source, context, and remediation. Suppressive false-positive actions are not shown here because the current backend does not store an auditable reason."
        actions={
          !finding.not_tested ? (
            <Button variant="outline" disabled={triaging || finding.triage_status === "fixed"} onClick={() => void markFixed()}>
              <CheckCircle2 className="size-4" />
              {finding.triage_status === "fixed" ? "Marked fixed" : "Mark as fixed"}
            </Button>
          ) : null
        }
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_360px]">
        <SectionCard
          title="Finding context"
          description="Everything shown below comes from the stored finding record for this scan."
        >
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={finding.severity} />
              <span className="rounded-full border border-border px-2 py-1 text-xs text-muted-foreground">
                {finding.triage_status.replace("_", " ")}
              </span>
              <span className="rounded-full border border-border px-2 py-1 text-xs text-muted-foreground">
                {OWASP_CATEGORY_LABELS[finding.owasp_category] ?? finding.owasp_category}
              </span>
            </div>

            <div className="rounded-2xl border border-border bg-background/80 p-4">
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

          <SectionCard title="Status" description="Finding status is currently limited to the backend states the product enforces today.">
            <div className="space-y-3 text-sm leading-6 text-muted-foreground">
              <p>Current status: <strong className="text-foreground">{finding.triage_status.replace("_", " ")}</strong></p>
              <p>False-positive suppression is intentionally hidden in this redesign until the backend can require and retain an auditable reason.</p>
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}

function MetaPanel({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-border bg-background/80 p-4">
      <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <p className="mt-2 text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

function SectionBody({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-border bg-background/80 p-4">
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{body}</p>
    </div>
  );
}
