"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ApiError } from "@/shared/api";
import { agentApi } from "@/entities/agent";
import type { Policies, PolicyAuditEntry } from "@/entities/agent";
import {
  EmptyState,
  PageHeader,
  Panel,
  PanelBody,
  PanelHeader,
  PanelSubtitle,
  PanelTableWrap,
  PanelTitle,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
} from "@/shared/ui";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Skeleton } from "@/shared/ui/skeleton";
import { Switch } from "@/shared/ui/switch";
import { formatDateTime } from "@/shared/lib/format";

const POLICY_COPY: Record<keyof Policies, { label: string; description: string }> = {
  block_grade_d: {
    label: "Block MCP servers graded D",
    description:
      "A server its own scan called high risk. Only applies once a scan has graded it: an unscanned server is unproven, not condemned.",
  },
  require_approval_grade_c: {
    label: "Require approval for MCP servers graded C",
    description: "Usable, but worth a person deciding each time rather than a default.",
  },
  block_unattended_shell: {
    label: "Block agents that run commands without asking",
    description:
      "Claude Code's bypassPermissions and Codex's approval_policy = never. Neither widens what an agent can reach; both remove the check on everything it already reaches.",
  },
  block_unrestricted_network: {
    label: "Block agents with unrestricted network access",
    description: "An agent that can reach any host, not a named list of them.",
  },
};

const ORDER = Object.keys(POLICY_COPY) as (keyof Policies)[];

export function PoliciesPage() {
  const [policies, setPolicies] = useState<Policies | null>(null);
  const [audit, setAudit] = useState<PolicyAuditEntry[] | null>(null);
  const [saving, setSaving] = useState<keyof Policies | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([agentApi.getPolicies(), agentApi.listPolicyAudit()])
      .then(([current, entries]) => {
        if (cancelled) return;
        setPolicies(current);
        setAudit(entries);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load your policies.");
        setPolicies(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function toggle(field: keyof Policies, value: boolean) {
    if (!policies) return;
    const next = { ...policies, [field]: value };
    setSaving(field);
    try {
      setPolicies(await agentApi.updatePolicies(next));
      setAudit(await agentApi.listPolicyAudit());
      toast.success(value ? "Policy switched on" : "Policy switched off");
    } catch (err) {
      // Put the switch back rather than leaving the page claiming a state
      // the server never accepted.
      setPolicies(policies);
      toast.error(err instanceof ApiError ? err.message : "Could not save that policy.");
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        pretitle="AI security"
        title="Policies"
        description="Turn a trust grade into a decision. Everything here is off until you switch it on."
      />

      {/* The line between advice and enforcement, stated where someone is
          about to cross it. */}
      <Alert>
        <AlertTitle>These are labels, not enforcement on your machines</AlertTitle>
        <AlertDescription>
          Aevrin cannot reach your devices, so a blocked server keeps running until you change it
          there. What these switches do is mark, on every page, which servers and agents your own
          rules object to — and record who changed the rules.
        </AlertDescription>
      </Alert>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load policies</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Panel>
        <PanelHeader>
          <PanelTitle>Enforcement</PanelTitle>
          <PanelSubtitle>
            When two apply at once, the stricter answer wins: the looser one is not a reason to
            ignore the stricter.
          </PanelSubtitle>
        </PanelHeader>
        <PanelBody className="flex flex-col gap-4">
          {policies === null && !error ? (
            <>
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </>
          ) : policies === null ? null : (
            ORDER.map((field) => (
              <div key={field} className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <label htmlFor={field} className="text-sm font-medium">
                    {POLICY_COPY[field].label}
                  </label>
                  <p className="mt-1 text-[13px] leading-5 text-muted-foreground">
                    {POLICY_COPY[field].description}
                  </p>
                </div>
                <Switch
                  id={field}
                  checked={policies[field]}
                  disabled={saving !== null}
                  onCheckedChange={(value: boolean) => void toggle(field, value)}
                />
              </div>
            ))
          )}
        </PanelBody>
      </Panel>

      <Panel>
        <PanelHeader>
          <PanelTitle>Change history</PanelTitle>
          <PanelSubtitle>
            Who changed which policy, when, and what it was before. Policy changes only, and never
            any secret or environment value.
          </PanelSubtitle>
        </PanelHeader>
        {audit === null ? (
          <PanelBody>
            <Skeleton className="h-10 w-full" />
          </PanelBody>
        ) : audit.length === 0 ? (
          <EmptyState
            title="No policy changes yet"
            body="Switching a policy on or off is recorded here. A change that alters nothing is not."
          />
        ) : (
          <PanelTableWrap>
            <Table>
              <THead>
                <TR>
                  <TH>When</TH>
                  <TH>Who</TH>
                  <TH>What changed</TH>
                </TR>
              </THead>
              <TBody>
                {audit.map((entry) => {
                  const changed = ORDER.filter(
                    (field) => entry.before?.[field] !== entry.after?.[field],
                  );
                  return (
                    <TR key={entry.id}>
                      <TD className="text-muted-foreground">{formatDateTime(entry.created_at)}</TD>
                      <TD>{entry.actor}</TD>
                      <TD>
                        <ul className="flex flex-col gap-1">
                          {changed.map((field) => (
                            <li key={field} className="text-sm">
                              {POLICY_COPY[field].label}:{" "}
                              <span className="font-medium">
                                {entry.after?.[field] ? "on" : "off"}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
          </PanelTableWrap>
        )}
      </Panel>
    </div>
  );
}
