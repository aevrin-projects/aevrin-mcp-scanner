"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

type Analytics = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const RANGES = [7, 30, 90];

export default function AdminAnalyticsPage() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.adminAnalytics(days));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load analytics.");
    }
  }, [days]);

  useEffect(() => {
    const id = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(id);
  }, [load]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!data) return <Skeleton className="h-96 rounded-xl" />;

  const money = (paise: number) => `₹${(paise / 100).toLocaleString()}`;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Computed from Aevrin&apos;s own database. No third-party analytics vendor, so nothing about your
            customers leaves your infrastructure.
          </p>
        </div>
        <div className="flex gap-1.5">
          {RANGES.map((r) => (
            <Button key={r} size="sm" variant={days === r ? "default" : "outline"} onClick={() => setDays(r)}>
              {r}d
            </Button>
          ))}
        </div>
      </div>

      <Section title="Traffic">
        <Stats
          items={[
            ["Pageviews", data.pageviews_in_window],
            ["Visitors", data.visitors_in_window],
            ["Top page", data.top_pages?.[0]?.path ?? "—"],
          ]}
        />
        {data.pageviews_in_window === 0 ? (
          <Note>
            No pageviews recorded yet. Collection starts the moment this deploy is live — it counts visits from
            then on and cannot backfill history it never saw.
          </Note>
        ) : (
          <div className="grid gap-5 lg:grid-cols-2">
            <Table
              caption="Top pages"
              head={["Path", "Views", "Visitors"]}
              rows={(data.top_pages ?? []).map((p: any) => [p.path, p.views, p.visitors])} // eslint-disable-line @typescript-eslint/no-explicit-any
            />
            <Table
              caption="Referrers"
              head={["Source", "Views"]}
              rows={(data.top_referrers ?? []).map((r: any) => [r.referrer, r.views])} // eslint-disable-line @typescript-eslint/no-explicit-any
            />
            <Table
              caption="Countries"
              head={["Country", "Views"]}
              rows={(data.countries ?? []).map((c: any) => [c.country, c.views])} // eslint-disable-line @typescript-eslint/no-explicit-any
            />
            <KeyValue caption="Devices" data={data.devices ?? {}} />
          </div>
        )}
      </Section>

      <Section title="Growth">
        <Stats
          items={[
            ["Accounts", data.accounts_total],
            [`Signups (${days}d)`, data.signups_in_window],
            ["Flagged", data.flagged_accounts],
          ]}
        />
        <div className="grid gap-5 lg:grid-cols-2">
          <KeyValue caption="Plans (effective)" data={data.plan_distribution ?? {}} />
          <KeyValue caption="Account status" data={data.status_distribution ?? {}} />
        </div>
        <Spark caption="Signups per day" points={(data.signups_by_day ?? []).map((d: any) => d.count)} /> {/* eslint-disable-line @typescript-eslint/no-explicit-any */}
      </Section>

      <Section title="CLI and hook adoption">
        <Stats
          items={[
            ["CLI authenticated", data.cli_authenticated_accounts],
            [`CLI active (${days}d)`, data.cli_active_accounts],
            [`Hook active (${days}d)`, data.hook_active_accounts],
            ["Hook cached targets", data.hook_cached_targets],
          ]}
        />
        <KeyValue caption="Device authorizations by client" data={data.device_authorizations ?? {}} />
        <Note>
          Installs themselves aren&apos;t observable from here — npm and PyPI download counts live with those
          registries. What this measures is authentication and actual use, which is the stronger signal anyway:
          an install that never authenticates never became a user.
        </Note>
      </Section>

      <Section title="Usage">
        <Stats
          items={[
            [`Scans (${days}d)`, data.scans_in_window],
            ["Scans all time", data.scans_total],
            ["Avg findings/scan", data.avg_findings_per_scan],
            ["Auto-fix PRs", data.autofix_prs_opened],
          ]}
        />
        <div className="grid gap-5 lg:grid-cols-2">
          <KeyValue caption="By surface" data={data.scans_by_source ?? {}} />
          <KeyValue caption="Outcomes" data={data.scan_outcomes ?? {}} />
        </div>
        <Spark caption="Scans per day" points={(data.scans_by_day ?? []).map((d: any) => d.count)} /> {/* eslint-disable-line @typescript-eslint/no-explicit-any */}
      </Section>

      <Section title="Revenue">
        <Stats
          items={[
            ["Paid payments", data.payments_paid_count],
            ["Revenue all time", money(data.revenue_paise_total ?? 0)],
            [`Revenue (${days}d)`, money(data.revenue_paise_in_window ?? 0)],
          ]}
        />
        <KeyValue caption="Checkouts by status" data={data.payments_by_status ?? {}} />
        <Note>
          &quot;Created&quot; checkouts were started but never completed. A high ratio there is a payment-flow
          problem, not a demand problem.
        </Note>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <h2 className="text-sm font-medium tracking-[0.06em] text-muted-foreground uppercase">{title}</h2>
      {children}
    </section>
  );
}

function Stats({ items }: { items: Array<[string, unknown]> }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {items.map(([label, value]) => (
        <div key={label} className="rounded-xl border border-border bg-card px-4 py-3">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="mt-1 truncate text-2xl font-semibold tracking-tight tabular-nums">{String(value ?? "—")}</p>
        </div>
      ))}
    </div>
  );
}

function KeyValue({ caption, data }: { caption: string; data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-[13px] font-medium">{caption}</p>
      {entries.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">No data yet.</p>
      ) : (
        <dl className="mt-3 space-y-1.5">
          {entries.map(([k, v]) => (
            <div key={k} className="flex items-center justify-between text-sm">
              <dt className="text-muted-foreground capitalize">{k.replace(/_/g, " ")}</dt>
              <dd className="tabular-nums">{String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function Table({ caption, head, rows }: { caption: string; head: string[]; rows: unknown[][] }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-[13px] font-medium">{caption}</p>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">No data yet.</p>
      ) : (
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              {head.map((h) => (
                <th key={h} className="pb-1.5 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-border/60">
                {r.map((cell, j) => (
                  <td key={j} className={`py-1.5 ${j === 0 ? "truncate" : "tabular-nums"}`}>
                    {String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/** Relative bars only — the numbers beside them carry the actual values. */
function Spark({ caption, points }: { caption: string; points: number[] }) {
  const max = Math.max(...points, 1);
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-[13px] font-medium">{caption}</p>
      {points.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">No data in this window.</p>
      ) : (
        <div className="mt-3 flex h-24 items-end gap-1">
          {points.map((p, i) => (
            <div
              key={i}
              title={String(p)}
              className="min-w-1 flex-1 rounded-sm bg-brand/60"
              style={{ height: `${Math.max((p / max) * 100, 3)}%` }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="text-xs leading-relaxed text-muted-foreground">{children}</p>;
}
