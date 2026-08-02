"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { Finding, Scan, ScanStage, Severity } from "@/lib/types";
import { OWASP_CATEGORY_LABELS, STAGE_LABELS, STAGE_ORDER } from "@/lib/types";
import { verdict } from "@/lib/scoring";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { SeverityBadge } from "@/components/severity-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { CheckCircle2, CircleDashed, Loader2, MinusCircle, XCircle, AlertTriangle } from "lucide-react";

const POLL_INTERVAL_MS = 2000;

const STAGE_ICON: Record<ScanStage["status"], React.ReactNode> = {
  pending: <CircleDashed className="size-4 text-muted-foreground" />,
  running: <Loader2 className="size-4 animate-spin text-foreground" />,
  done: <CheckCircle2 className="size-4 text-severity-low" />,
  failed: <XCircle className="size-4 text-severity-critical" />,
  skipped: <MinusCircle className="size-4 text-muted-foreground" />,
};

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

export function ScanDetailClient({ scanId }: { scanId: string }) {
  const [scan, setScan] = useState<Scan | null>(null);
  const [stages, setStages] = useState<ScanStage[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const [scanData, stagesData] = await Promise.all([
        api.getScan(scanId),
        api.getScanStages(scanId),
      ]);
      setScan(scanData);
      setStages(stagesData);
      setLoadError(null);

      if (scanData.status === "completed" || scanData.status === "failed") {
        const findingsData = await api.getScanFindings(scanId);
        setFindings(findingsData);
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not load this scan.";
      setLoadError(message);
      toast.error(message);
    }
  }, [scanId]);

  useEffect(() => {
    // Fetch-on-mount + poll: `load` synchronizes component state with the
    // server-side scan status, which is exactly what an effect is for here —
    // there's no non-effect way to start polling an external resource.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
    intervalRef.current = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [load]);

  if (loadError && !scan) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-12">
        <Alert variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>Could not load scan</AlertTitle>
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!scan) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-12 flex flex-col gap-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const inProgress = scan.status === "queued" || scan.status === "running";

  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-muted-foreground">{scan.target_type.replace("_", " ")}</p>
          <h1 className="font-mono text-lg font-medium">{scan.target}</h1>
        </div>
        {scan.status === "completed" && <ExportButton scanId={scanId} />}
      </div>

      {inProgress && <ProgressView stages={stages} />}

      {scan.status === "failed" && (
        <Alert variant="destructive" className="mt-8">
          <AlertTriangle className="size-4" />
          <AlertTitle>Scan failed</AlertTitle>
          <AlertDescription>
            {scan.error ?? "Every stage failed to complete. See stage errors below."}
            <ul className="mt-2 list-disc pl-5">
              {stages
                .filter((s) => s.status === "failed" && s.error)
                .map((s) => (
                  <li key={s.name}>
                    {STAGE_LABELS[s.name]}: {s.error}
                  </li>
                ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {scan.status === "completed" && <ResultsView scan={scan} findings={findings} />}
    </div>
  );
}

function ProgressView({ stages }: { stages: ScanStage[] }) {
  const ordered = STAGE_ORDER.map(
    (name) => stages.find((s) => s.name === name) ?? { name, status: "pending" as const, error: null, started_at: null, finished_at: null },
  );
  const doneCount = ordered.filter((s) => s.status === "done" || s.status === "skipped").length;
  const percent = Math.round((doneCount / ordered.length) * 100);

  return (
    <Card className="mt-8" data-testid="scan-progress">
      <CardHeader>
        <CardTitle className="text-base font-medium">Scanning…</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <Progress value={percent} />
        <ul className="flex flex-col gap-3">
          {ordered.map((stage) => (
            <li key={stage.name} className="flex items-center gap-3 text-sm">
              {STAGE_ICON[stage.status]}
              <span className={stage.status === "pending" ? "text-muted-foreground" : ""}>
                {STAGE_LABELS[stage.name]}
              </span>
              {stage.status === "skipped" && (
                <span className="text-xs text-muted-foreground">(not applicable)</span>
              )}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function ResultsView({ scan, findings }: { scan: Scan; findings: Finding[] }) {
  const router = useRouter();
  const counts = Object.fromEntries(SEVERITY_ORDER.map((s) => [s, 0])) as Record<Severity, number>;
  for (const f of findings) {
    if (!f.not_tested) counts[f.severity]++;
  }
  const realFindings = findings.filter((f) => !f.not_tested);
  const notTested = findings.filter((f) => f.not_tested);

  return (
    <div className="mt-8 flex flex-col gap-8" data-testid="scan-results">
      <Card>
        <CardContent className="flex items-center justify-between pt-6">
          <div>
            <div className="text-4xl font-semibold tabular-nums">{scan.score}</div>
            <p className="text-sm text-muted-foreground">{scan.score !== null && verdict(scan.score)}</p>
          </div>
          <div className="flex gap-2">
            {SEVERITY_ORDER.filter((s) => s !== "info").map((s) => (
              <div key={s} className="flex flex-col items-center gap-1">
                <SeverityBadge severity={s} />
                <span className="text-sm tabular-nums">{counts[s]}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">
          Findings ({realFindings.length})
        </h2>
        {realFindings.length === 0 ? (
          <p className="text-sm text-muted-foreground">No findings — clean scan.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Severity</TableHead>
                <TableHead>Title</TableHead>
                <TableHead>OWASP category</TableHead>
                <TableHead>Tool</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {realFindings
                .sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity))
                .map((f) => (
                  <TableRow
                    key={f.id}
                    className="cursor-pointer"
                    onClick={() => router.push(`/scans/${scan.id}/findings/${f.id}`)}
                  >
                    <TableCell>
                      <SeverityBadge severity={f.severity} />
                    </TableCell>
                    <TableCell className="font-medium">{f.title}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {OWASP_CATEGORY_LABELS[f.owasp_category] ?? f.owasp_category}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{f.tool}</TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        )}
      </div>

      {notTested.length > 0 && (
        <Alert>
          <AlertTriangle className="size-4" />
          <AlertTitle>Coverage limitation</AlertTitle>
          <AlertDescription>{notTested[0].description}</AlertDescription>
        </Alert>
      )}
    </div>
  );
}

function ExportButton({ scanId }: { scanId: string }) {
  const [exporting, setExporting] = useState(false);
  return (
    <Button
      variant="outline"
      disabled={exporting}
      onClick={async () => {
        setExporting(true);
        try {
          const { url } = await api.exportReport(scanId);
          window.open(url, "_blank");
        } catch (err) {
          toast.error(err instanceof ApiError ? err.message : "Could not export report.");
        } finally {
          setExporting(false);
        }
      }}
    >
      {exporting ? "Exporting…" : "Export report"}
    </Button>
  );
}
