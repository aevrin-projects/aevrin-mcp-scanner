"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/shared/api";
import { adminApi } from "@/entities/admin";
import type { AdminAuditEntry, AdminLoginAttempt } from "@/entities/admin";
import { Input } from "@/shared/ui/input";
import { Skeleton } from "@/shared/ui/skeleton";
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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Audit log</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Append-only. Rows cannot be edited or deleted — a database trigger blocks both, including
          for the service role. Use the filters below to narrow the view.
        </p>
      </div>

      {failedRecently > 0 ? (
        <p className="rounded-xl border border-severity-medium/40 bg-severity-medium/10 px-4 py-3 text-sm text-severity-medium">
          {failedRecently} failed admin sign-in attempt{failedRecently === 1 ? "" : "s"} recently; see the table
          below.
        </p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <Input value={action} onChange={(e) => setAction(e.target.value)} placeholder="Filter by action" aria-label="Filter by action" />
        <Input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="Filter by target user id" aria-label="Filter by target user id" />
        <Input
          type="date"
          value={since}
          onChange={(e) => setSince(e.target.value)}
          aria-label="Show entries on or after this date"
          title="Show entries on or after this date"
        />
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {!entries ? (
        <Skeleton className="h-72 rounded-xl" />
      ) : entries.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border px-5 py-10 text-center text-sm text-muted-foreground">
          Nothing recorded yet.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full min-w-[900px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs tracking-[0.06em] text-muted-foreground uppercase">
                <th className="px-4 py-2.5 font-medium">When</th>
                <th className="px-4 py-2.5 font-medium">Admin</th>
                <th className="px-4 py-2.5 font-medium">Action</th>
                <th className="px-4 py-2.5 font-medium">Target</th>
                <th className="px-4 py-2.5 font-medium">Reason</th>
                <th className="px-4 py-2.5 font-medium">IP</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} className="border-b border-border/60 last:border-0">
                  <td className="px-4 py-2.5 whitespace-nowrap text-muted-foreground">{formatDateTime(e.created_at)}</td>
                  <td className="px-4 py-2.5">{e.actor_email ?? e.actor_user_id}</td>
                  <td className="px-4 py-2.5 font-mono text-[12px]">{e.action}</td>
                  <td className="px-4 py-2.5">{e.target_email ?? e.target_user_id ?? e.target_resource ?? "-"}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">{e.reason ?? "-"}</td>
                  <td className="px-4 py-2.5 font-mono text-[12px] text-muted-foreground">{e.ip_address ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div>
        <h2 className="text-sm font-medium">Recent admin sign-in attempts</h2>
        {!attempts ? (
          <Skeleton className="mt-3 h-40 rounded-xl" />
        ) : attempts.length === 0 ? (
          <p className="mt-3 text-sm text-muted-foreground">None recorded.</p>
        ) : (
          <div className="mt-3 overflow-x-auto rounded-xl border border-border">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs tracking-[0.06em] text-muted-foreground uppercase">
                  <th className="px-4 py-2.5 font-medium">When</th>
                  <th className="px-4 py-2.5 font-medium">Email</th>
                  <th className="px-4 py-2.5 font-medium">Result</th>
                  <th className="px-4 py-2.5 font-medium">IP</th>
                </tr>
              </thead>
              <tbody>
                {attempts.map((a) => (
                  <tr key={a.id} className="border-b border-border/60 last:border-0">
                    <td className="px-4 py-2.5 whitespace-nowrap text-muted-foreground">{formatDateTime(a.created_at)}</td>
                    <td className="px-4 py-2.5">{a.email ?? "-"}</td>
                    <td className="px-4 py-2.5">
                      {a.succeeded ? (
                        <span className="text-chart-1">ok</span>
                      ) : (
                        <span className="text-severity-high">{a.failure_reason ?? "failed"}</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[12px] text-muted-foreground">{a.ip_address ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
