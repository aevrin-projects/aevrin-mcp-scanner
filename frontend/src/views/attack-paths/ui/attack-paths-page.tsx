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
  TechnicalDetails,
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
        setError(err instanceof ApiError ? err.message : "We could not load the attack paths.");
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
        description="Step-by-step ways a mistake or a trick could get from one of your agents to something important, like your passwords and keys. Each step was read from real settings."
      />

      <Alert>
        <AlertTitle>Only what we could prove</AlertTitle>
        <AlertDescription>
          <p>
            A path shows up here only when we found every step in the agent&apos;s real settings. We do
            not list guesses like &ldquo;it might reach this, which might reach that&rdquo;.
          </p>
          <TechnicalDetails className="mt-2">
            <p>
              A path appears only when every step was read out of a configuration. An agent allowed
              only <code className="font-mono">Bash(npm run *)</code> with AWS credentials on disk
              produces no path, because nothing establishes that it may run{" "}
              <code className="font-mono">aws</code>.
            </p>
          </TechnicalDetails>
        </AlertDescription>
      </Alert>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>We could not load the attack paths</AlertTitle>
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
            title="No attack paths found"
            body="We did not find every step of a path in the settings your computers reported. That means we could not prove one, not that none exists."
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
                  {path.severity === "critical" ? "Very serious" : path.severity === "high" ? "Serious" : "Worth fixing"}
                </Badge>
                <Badge
                  variant="outline"
                  className="rounded-full px-2 py-0.5 text-xs text-muted-foreground"
                >
                  {path.confidence === "high" ? "We are sure" : "We are fairly sure"}
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
                    <TH>What we found</TH>
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
                <span className="font-medium">What should I do? </span>
                {path.remediation}
              </p>
            </PanelBody>
          </Panel>
        ))
      )}
    </div>
  );
}
