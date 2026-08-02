"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { Finding } from "@/lib/types";
import { OWASP_CATEGORY_LABELS } from "@/lib/types";
import { SeverityBadge } from "@/components/severity-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ArrowLeft, AlertTriangle, CheckCircle2, Ban } from "lucide-react";

export function FindingDetailClient({ scanId, findingId }: { scanId: string; findingId: string }) {
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
        toast.error(message);
      });
  }, [findingId]);

  async function triage(status: "fixed" | "false_positive") {
    setTriaging(true);
    try {
      const updated = await api.triageFinding(findingId, status);
      setFinding(updated);
      toast.success(status === "fixed" ? "Marked as fixed" : "Marked as false positive");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not update this finding.");
    } finally {
      setTriaging(false);
    }
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-12">
        <Alert variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>Could not load finding</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!finding) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-12 flex flex-col gap-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  const location = finding.file_path
    ? `${finding.file_path}${finding.line_start ? `:${finding.line_start}` : ""}`
    : finding.manifest_field
      ? `${finding.tool_name_in_manifest ? finding.tool_name_in_manifest + " → " : ""}${finding.manifest_field}`
      : null;

  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <Link
        href={`/scans/${scanId}`}
        className="mb-6 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" /> Back to results
      </Link>

      <div className="flex items-start justify-between gap-4">
        <h1 className="text-xl font-semibold">{finding.title}</h1>
        <SeverityBadge severity={finding.severity} className="shrink-0" />
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <Badge variant="outline">{OWASP_CATEGORY_LABELS[finding.owasp_category] ?? finding.owasp_category}</Badge>
        <span>via {finding.tool}</span>
        {finding.verified !== null && (
          <Badge variant={finding.verified ? "destructive" : "outline"}>
            {finding.verified ? "Verified live" : "Unverified"}
          </Badge>
        )}
        <Badge variant={finding.triage_status === "open" ? "outline" : "secondary"}>
          {finding.triage_status.replace("_", " ")}
        </Badge>
      </div>

      {location && (
        <p className="mt-4 rounded-md bg-muted px-3 py-2 font-mono text-sm">{location}</p>
      )}

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">Description</CardTitle>
        </CardHeader>
        <CardContent className="whitespace-pre-wrap text-sm">{finding.description}</CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">Remediation</CardTitle>
        </CardHeader>
        <CardContent className="whitespace-pre-wrap text-sm">{finding.remediation}</CardContent>
      </Card>

      <div className="mt-6 flex gap-3">
        <Button
          variant="outline"
          disabled={triaging || finding.triage_status === "fixed"}
          onClick={() => triage("fixed")}
        >
          <CheckCircle2 className="size-4" /> Mark as fixed
        </Button>
        <Button
          variant="outline"
          disabled={triaging || finding.triage_status === "false_positive"}
          onClick={() => triage("false_positive")}
        >
          <Ban className="size-4" /> Mark as false positive
        </Button>
      </div>
    </div>
  );
}
