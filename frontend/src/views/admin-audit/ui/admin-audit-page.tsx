"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, ShieldAlert, X } from "lucide-react";
import { ApiError } from "@/shared/api";
import { adminApi } from "@/entities/admin";
import type { AdminAuditEntry, AdminLoginAttempt } from "@/entities/admin";
import { Alert, AlertDescription, AlertTitle } from "@/shared/ui/alert";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { EmptyState } from "@/shared/ui/empty-state";
import { Input } from "@/shared/ui/input";
import { PageHeader } from "@/shared/ui/page-header";
import { Panel, PanelTableWrap } from "@/shared/ui/panel";
import { Skeleton } from "@/shared/ui/skeleton";
import { TBody, TD, TH, THead, TR, Table } from "@/shared/ui/data-table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import { formatDateTime } from "@/shared/lib/format";

export function AdminAuditPage() {
  const [entries, setEntries] = useState<AdminAuditEntry[] | null>(null);
  const [attempts, setAttempts] = useState<AdminLoginAttempt[] | null>(null);
  const [action, setAction] = useState("");
  const [target, setTarget] = useState("");
  const [since, setSince] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [log, logins] = await Promise.all([
        adminApi.getAudit({ action: action || undefined, target: target || undefined, since: since || undefined }),
        adminApi.getLoginAttempts(),
      ]);
      setEntries(log);
      setAttempts(logins);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the audit log.");
    }
  }, [action, target, since]);

  useEffect(() => {
    const id = window.setTimeout(() => void load(), 250);
    return () => window.clearTimeout(id);
  }, [load]);

  const failedRecently = (attempts ?? []).filter((a) => !a.succeeded).length;
  const filtered = Boolean(action || target || since);

  return (
    <>
      <PageHeader
        pretitle="Security"
        title="Audit log"
        description="Append-only. Rows cannot be edited or deleted — a database trigger blocks both, including for the service role."
      />

      {failedRecently > 0 ? (
        <Alert variant="destructive">
          <ShieldAlert className="size-4" />
          <AlertTitle>
            {failedRecently} failed admin sign-in attempt{failedRecently === 1 ? "" : "s"} recently
          </AlertTitle>
          <AlertDescription>
            Check the sign-in attempts tab below for the addresses and reasons.
          </AlertDescription>
        </Alert>
      ) : null}

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Tabs defaultValue="activity">
        <TabsList>
          <TabsTrigger value="activity">
            Activity{entries ? ` (${entries.length})` : ""}
          </TabsTrigger>
          <TabsTrigger value="signins">
            Sign-in attempts{attempts ? ` (${attempts.length})` : ""}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="activity" className="mt-4 flex flex-col gap-4">
          <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto_auto]">
            <Input
              value={action}
              onChange={(e) => setAction(e.target.value)}
              className="h-8"
              placeholder="Filter by action"
              aria-label="Filter by action"
            />
            <Input
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="h-8"
              placeholder="Filter by target user id"
              aria-label="Filter by target user id"
            />
            <Input
              type="date"
              value={since}
              onChange={(e) => setSince(e.target.value)}
              className="h-8"
              aria-label="Show entries on or after this date"
              title="Show entries on or after this date"
            />
            {filtered ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setAction("");
                  setTarget("");
                  setSince("");
                }}
              >
                Reset
                <X className="size-4" />
              </Button>
            ) : null}
          </div>

          {!entries ? (
            <Skeleton className="h-72 rounded-lg" />
          ) : entries.length === 0 ? (
            <EmptyState
              title="Nothing recorded"
              body={
                filtered
                  ? "No entries match these filters. Reset them to see the whole log."
                  : "No administrative action has been recorded yet."
              }
            />
          ) : (
            <Panel>
              <PanelTableWrap>
                <Table className="min-w-[900px]">
                  <THead>
                    <TR>
                      <TH>When</TH>
                      <TH>Admin</TH>
                      <TH>Action</TH>
                      <TH>Target</TH>
                      <TH>Reason</TH>
                      <TH>IP</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {entries.map((e) => (
                      <TR key={e.id}>
                        <TD className="whitespace-nowrap text-muted-foreground">
                          {formatDateTime(e.created_at)}
                        </TD>
                        <TD>{e.actor_email ?? e.actor_user_id}</TD>
                        <TD>
                          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{e.action}</code>
                        </TD>
                        <TD>{e.target_email ?? e.target_user_id ?? e.target_resource ?? "—"}</TD>
                        <TD className="text-muted-foreground">{e.reason ?? "—"}</TD>
                        <TD className="font-mono text-xs text-muted-foreground">{e.ip_address ?? "—"}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </PanelTableWrap>
            </Panel>
          )}
        </TabsContent>

        <TabsContent value="signins" className="mt-4">
          {!attempts ? (
            <Skeleton className="h-40 rounded-lg" />
          ) : attempts.length === 0 ? (
            <EmptyState title="No sign-in attempts recorded" />
          ) : (
            <Panel>
              <PanelTableWrap>
                <Table className="min-w-[640px]">
                  <THead>
                    <TR>
                      <TH>When</TH>
                      <TH>Email</TH>
                      <TH>Result</TH>
                      <TH>IP</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {attempts.map((a) => (
                      <TR key={a.id}>
                        <TD className="whitespace-nowrap text-muted-foreground">
                          {formatDateTime(a.created_at)}
                        </TD>
                        <TD>{a.email ?? "—"}</TD>
                        <TD>
                          {/* An icon and a word, not just a colour: a red/green
                              distinction is invisible to a large minority of
                              readers, and this is a security table. */}
                          {a.succeeded ? (
                            <Badge
                              variant="outline"
                              className="border-chart-1/40 bg-chart-1/10 text-chart-1"
                            >
                              <CheckCircle2 className="size-3" />
                              Succeeded
                            </Badge>
                          ) : (
                            <Badge
                              variant="outline"
                              className="border-severity-high/40 bg-severity-high/10 text-severity-high"
                            >
                              <ShieldAlert className="size-3" />
                              {a.failure_reason ?? "Failed"}
                            </Badge>
                          )}
                        </TD>
                        <TD className="font-mono text-xs text-muted-foreground">{a.ip_address ?? "—"}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </PanelTableWrap>
            </Panel>
          )}
        </TabsContent>
      </Tabs>
    </>
  );
}
