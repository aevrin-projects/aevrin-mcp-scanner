"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Sparkles } from "lucide-react";
import { ApiError } from "@/shared/api";
import { agentApi, AGENT_KIND_LABELS, ScopeBadge } from "@/entities/agent";
import type { Skill } from "@/entities/agent";
import {
  EmptyState,
  PageHeader,
  Panel,
  PanelBody,
  PanelTableWrap,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Table,
} from "@/shared/ui";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Input } from "@/shared/ui/input";
import { Skeleton } from "@/shared/ui/skeleton";

export function SkillsPage() {
  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    agentApi
      .listSkills()
      .then((result) => {
        if (!cancelled) setSkills(result);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Could not load your skills.");
        setSkills([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return skills ?? [];
    return (skills ?? []).filter((skill) =>
      [skill.name, skill.description ?? "", skill.hostname].some((field) =>
        field.toLowerCase().includes(needle),
      ),
    );
  }, [skills, query]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        pretitle="AI security"
        title="Skills"
        description="Instructions your agents load on their own, and where each one came from."
      />

      {/* Not correlated the way MCP servers are, and saying so beats a
          number that looks authoritative and is not. */}
      <Alert>
        <AlertTitle>One row per installation</AlertTitle>
        <AlertDescription>
          A skill is a folder of prose on a machine, with no URL or package to pin it to. Two skills
          sharing a name are not evidence of being the same skill, so they are listed separately
          rather than merged.
        </AlertDescription>
      </Alert>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load skills</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {skills === null ? (
        <Panel>
          <PanelBody className="flex flex-col gap-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </PanelBody>
        </Panel>
      ) : skills.length === 0 && !error ? (
        <Panel>
          <EmptyState
            icon={<Sparkles />}
            title="No skills reported"
            body="Skills appear here once a device that has them reports in."
          />
        </Panel>
      ) : skills.length === 0 ? null : (
        <Panel>
          <PanelBody>
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search skills"
              aria-label="Search skills"
              className="sm:max-w-xs"
            />
          </PanelBody>
          <PanelTableWrap>
            <Table>
              <THead>
                <TR>
                  <TH>Skill</TH>
                  <TH>Scope</TH>
                  <TH>Agent</TH>
                  <TH>Device</TH>
                  <TH>Source</TH>
                </TR>
              </THead>
              <TBody>
                {visible.map((skill) => (
                  <TR key={`${skill.agent_id}:${skill.source_path}`}>
                    <TD>
                      <span className="font-medium">{skill.name}</span>
                      {skill.description ? (
                        <span className="block text-xs text-muted-foreground">{skill.description}</span>
                      ) : null}
                    </TD>
                    <TD>
                      <ScopeBadge scope={skill.scope} />
                    </TD>
                    <TD>
                      <Link href={`/agents/${skill.agent_id}`} className="hover:underline">
                        {AGENT_KIND_LABELS[skill.agent_type]}
                      </Link>
                    </TD>
                    <TD className="text-muted-foreground">{skill.hostname}</TD>
                    <TD className="truncate font-mono text-xs text-muted-foreground">
                      {skill.source_path}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </PanelTableWrap>
          {visible.length === 0 ? <EmptyState title="No skills match this search" /> : null}
        </Panel>
      )}
    </div>
  );
}
