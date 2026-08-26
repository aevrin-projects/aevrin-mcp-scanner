"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronRight, ShieldCheck } from "lucide-react";
import { ApiError } from "@/shared/api";
import { agentApi, AGENT_KIND_LABELS } from "@/entities/agent";
import type { AttackPath } from "@/entities/agent";
import {
  EmptyState,
  PageHeader,
  Panel,
  PanelBody,
  PanelHeader,
  PanelSubtitle,
  PanelTitle,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
} from "@/shared/ui";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Badge } from "@/shared/ui/badge";
import { Skeleton } from "@/shared/ui/skeleton";
import { cn } from "@/shared/lib/utils";

const SEVERITY_CLASSES: Record<AttackPath["severity"], string> = {
  critical: "border-severity-critical/40 bg-severity-critical/10 text-severity-critical",
  high: "border-severity-high/40 bg-severity-high/10 text-severity-high",
  medium: "border-severity-medium/40 bg-severity-medium/10 text-severity-medium",
};

/**
 * Source, steps, target, as a row of chips rather than a graph. The chain is
 * short and linear; a force-directed diagram of four nodes is decoration, and
 * decoration is not something a screen reader can follow. The same chain is
 * repeated as a table below, which is the version that carries the evidence.
 */
function Chain({ path }: { path: AttackPath }) {
  return (
    <ol className="flex flex-wrap items-center gap-1.5">
      <li>
        <span className="rounded-md border border-border bg-muted px-2 py-1 text-xs font-medium">
          {path.source}
        </span>
      </li>
      {path.steps.map((step) => (
        <li key={step.label} className="flex items-center gap-1.5">
          <ChevronRight className="size-3.5 text-muted-foreground" aria-hidden="true" />
          <span className="rounded-md border border-border px-2 py-1 text-xs">{step.label}</span>
        </li>
      ))}
      <li className="flex items-center gap-1.5">
        <ChevronRight className="size-3.5 text-muted-foreground" aria-hidden="true" />
        <span className="rounded-md border border-severity-critical/40 bg-severity-critical/10 px-2 py-1 text-xs font-medium text-severity-critical">
          {path.target}
        </span>
      </li>
    </ol>
  );
}

export function AttackPathsPage() {
  const [paths, setPaths] = useState<AttackPath[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    agentApi
      .listAttackPaths()
      .then((result) => {
        if (!cancelled) setPaths(result);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load attack paths.");
        setPaths([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        pretitle="AI security"
        title="Attack paths"
        description="What an agent on one of your machines can reach, when there is evidence for every step."
      />

      <Alert>
        <AlertTitle>Evidence, not speculation</AlertTitle>
        <AlertDescription>
          A path appears only when every step was read out of a configuration. An agent that might
          reach a cloud that might reach production is three maybes chained together: it looks like a
          finding, is not one, and is deliberately absent here. An agent allowed only{" "}
          <code className="font-mono">Bash(npm run *)</code> with AWS credentials on disk produces no
          path, because nothing establishes that it may run <code className="font-mono">aws</code>.
        </AlertDescription>
      </Alert>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load attack paths</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {paths === null ? (
        <Panel>
          <PanelBody>
            <Skeleton className="h-24 w-full" />
          </PanelBody>
        </Panel>
      ) : paths.length === 0 && !error ? (
        <Panel>
          <EmptyState
            icon={<ShieldCheck />}
            title="No evidenced attack paths"
            body="Nothing your devices reported chains all the way to a resource. That is the absence of an evidenced path, not a guarantee that none exists."
          />
        </Panel>
      ) : (
        paths.map((path) => (
          <Panel key={`${path.agent_id}:${path.key}`}>
            <PanelHeader>
              <PanelTitle className="flex flex-wrap items-center gap-2">
                {path.title}
                <Badge
                  variant="outline"
                  className={cn("rounded-full px-2 py-0.5 text-xs", SEVERITY_CLASSES[path.severity])}
                >
                  {path.severity}
                </Badge>
                <Badge
                  variant="outline"
                  className="rounded-full px-2 py-0.5 text-xs text-muted-foreground"
                >
                  {path.confidence} confidence
                </Badge>
              </PanelTitle>
              <PanelSubtitle>
                <Link href={`/agents/${path.agent_id}`} className="hover:underline">
                  {AGENT_KIND_LABELS[path.agent_type]}
                </Link>{" "}
                on {path.hostname}
              </PanelSubtitle>
            </PanelHeader>
            <PanelBody className="flex flex-col gap-4">
              <Chain path={path} />

              <Table>
                <THead>
                  <TR>
                    <TH>Step</TH>
                    <TH>What it means</TH>
                    <TH>Evidence</TH>
                  </TR>
                </THead>
                <TBody>
                  {path.steps.map((step) => (
                    <TR key={step.label}>
                      <TD className="font-medium">{step.label}</TD>
                      <TD>{step.detail}</TD>
                      <TD className="font-mono text-xs text-muted-foreground">
                        {step.evidence.length ? step.evidence.join("; ") : "—"}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>

              <p className="text-sm">
                <span className="font-medium">How to break it: </span>
                {path.remediation}
              </p>
            </PanelBody>
          </Panel>
        ))
      )}
    </div>
  );
}
