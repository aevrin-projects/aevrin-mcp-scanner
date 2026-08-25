"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Gauge, Globe, TerminalSquare, TrendingUp, Users, Webhook } from "lucide-react";
import { ApiError } from "@/shared/api";
import { adminApi } from "@/entities/admin";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { Donut, RankedBars, TrendChart } from "./charts";

type Analytics = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
type UsageRow = {
  user_id: string;
  email: string | null;
  effective_tier: string;
  status: string;
  bucket: string;
  used: number;
  limit_value: number | null;
  is_override: boolean;
  pct: number | null;
};

const RANGES = [7, 30, 90];

const BUCKETS = ["cli", "hook", "dashboard"] as const;
const BUCKET_LABEL: Record<string, string> = {
  cli: "CLI",
  hook: "Hook",
  dashboard: "Dashboard",
};

// One hue per series, from the existing token set so both themes work.
const C = {
  brand: "var(--brand)",
  green: "var(--chart-1)",
  red: "var(--chart-2)",
  blue: "var(--chart-3)",
  amber: "var(--chart-4)",
  grey: "var(--chart-5)",
};
const PIE = [C.brand, C.green, C.amber, C.red, C.blue, C.grey];

export function AdminAnalyticsPage() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Analytics | null>(null);
  const [usage, setUsage] = useState<UsageRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [a, u] = await Promise.all([adminApi.getAnalytics(days), adminApi.getAccountUsage()]);
      setData(a);
      setUsage(u as UsageRow[]);
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
  if (!data || !usage) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28 rounded-xl" />
        <Skeleton className="h-72 rounded-xl" />
        <Skeleton className="h-72 rounded-xl" />
      </div>
    );
  }

  const money = (paise: number) => `₹${(paise / 100).toLocaleString()}`;
  const byDay = (rows: any[], key: string) => // eslint-disable-line @typescript-eslint/no-explicit-any
    (rows ?? []).map((r) => ({ day: String(r.day).slice(5), [key]: r[key] ?? r.count ?? r.views ?? 0 }));

  // Merge views + visitors onto one axis so the gap between them is readable.
  const traffic = (data.views_by_day ?? []).map((r: any) => ({ // eslint-disable-line @typescript-eslint/no-explicit-any
    day: String(r.day).slice(5),
    views: r.views ?? 0,
    visitors: r.visitors ?? 0,
  }));

  const toPie = (obj: Record<string, number>) =>
    Object.entries(obj ?? {}).map(([name, value]) => ({ name, value: Number(value) }));

  // Accounts grouped, so each row is one account across all four buckets.
  const accounts = new Map<string, { email: string; tier: string; status: string; buckets: Record<string, UsageRow> }>();
  for (const row of usage) {
    const entry = accounts.get(row.user_id) ?? {
      email: row.email ?? row.user_id,
      tier: row.effective_tier,
      status: row.status,
      buckets: {},
    };
    entry.buckets[row.bucket] = row;
    accounts.set(row.user_id, entry);
  }
  // Whoever is closest to a ceiling first; that's the upgrade conversation.
  const accountRows = [...accounts.entries()].sort(
    (a, b) => maxPct(b[1].buckets) - maxPct(a[1].buckets),
  );
  const nearLimit = accountRows.filter(([, a]) => maxPct(a.buckets) >= 80).length;
  const atLimit = accountRows.filter(([, a]) => maxPct(a.buckets) >= 100).length;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            From Aevrin&apos;s own database: no third-party vendor, nothing about customers leaves your
            infrastructure.
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

      {/* Headline numbers, each with its own icon so the row scans quickly. */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi icon={<Users className="size-4" />} label="Accounts" value={data.accounts_total} sub={`+${data.signups_in_window} in ${days}d`} />
        <Kpi icon={<Gauge className="size-4" />} label={`Scans (${days}d)`} value={data.scans_in_window} sub={`${data.scans_total} all time`} />
        <Kpi icon={<Globe className="size-4" />} label={`Visitors (${days}d)`} value={data.visitors_in_window} sub={`${data.pageviews_in_window} pageviews`} />
        <Kpi
          icon={<AlertTriangle className="size-4" />}
          label="At or near a limit"
          value={`${atLimit} / ${nearLimit}`}
          sub="at limit / over 80%"
          tone={atLimit > 0 ? "warn" : undefined}
        />
      </div>

      {/* ---------------------------------------------------- per account */}
      <Card
        title="Usage by account"
        subtitle="Against the limit actually enforced: an admin override wins over the plan default, and unlimited shows as ∞."
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs tracking-[0.06em] text-muted-foreground uppercase">
                <th className="px-3 py-2.5 font-medium">Account</th>
                <th className="px-3 py-2.5 font-medium">Plan</th>
                {BUCKETS.map((b) => (
                  <th key={b} className="px-3 py-2.5 font-medium">
                    {BUCKET_LABEL[b]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {accountRows.map(([userId, acct]) => (
                <tr key={userId} className="border-b border-border/60 last:border-0 hover:bg-muted/30">
                  <td className="px-3 py-2.5">
                    <Link href={`/admin/users/${userId}`} className="hover:text-brand-text">
                      {acct.email}
                    </Link>
                    {acct.status !== "active" ? (
                      <span className="ml-2 text-[11px] text-severity-high">{acct.status}</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2.5 capitalize">{acct.tier}</td>
                  {BUCKETS.map((b) => (
                    <td key={b} className="px-3 py-2.5">
                      <UsageCell row={acct.buckets[b]} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted-foreground">
          Counted from Postgres rather than the live Redis counters, so this stays correct, and keeps working,
          when Redis is unavailable.
        </p>
      </Card>

      {/* -------------------------------------------------------- traffic */}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card title="Traffic" subtitle="Pageviews and distinct daily visitors.">
          <TrendChart
            data={traffic}
            xKey="day"
            series={[
              { key: "views", label: "Views", color: C.brand },
              { key: "visitors", label: "Visitors", color: C.green, dashed: true },
            ]}
          />
          {data.pageviews_in_window === 0 ? (
            <p className="text-xs text-muted-foreground">
              Collection began when this deploy went live; it counts visits from then on and cannot backfill
              history it never saw.
            </p>
          ) : null}
        </Card>

        <Card title="Top pages">
          <RankedBars data={data.top_pages ?? []} labelKey="path" valueKey="views" color={C.brand} />
        </Card>

        <Card title="Referrers">
          <RankedBars data={data.top_referrers ?? []} labelKey="referrer" valueKey="views" color={C.blue} />
        </Card>

        <Card title="Devices">
          <Donut data={toPie(data.devices)} colors={PIE} />
          <Legend data={toPie(data.devices)} colors={PIE} />
        </Card>
      </div>

      {/* ---------------------------------------------------------- usage */}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card title="Scans per day">
          <TrendChart data={byDay(data.scans_by_day, "count")} xKey="day" series={[{ key: "count", label: "Scans", color: C.green }]} />
        </Card>
        <Card title="By surface" subtitle="Which product surface started each scan.">
          <Donut data={toPie(data.scans_by_source)} colors={PIE} />
          <Legend data={toPie(data.scans_by_source)} colors={PIE} />
        </Card>
        <Card title="Signups per day">
          <TrendChart data={byDay(data.signups_by_day, "count")} xKey="day" series={[{ key: "count", label: "Signups", color: C.brand }]} />
        </Card>
        <Card title="Plans" subtitle="Effective tier: a lapsed paid account counts as Free.">
          <Donut data={toPie(data.plan_distribution)} colors={PIE} />
          <Legend data={toPie(data.plan_distribution)} colors={PIE} />
        </Card>
      </div>

      {/* ------------------------------------------------- CLI + hook + $ */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Kpi icon={<TerminalSquare className="size-4" />} label="CLI authenticated" value={data.cli_authenticated_accounts} sub={`${data.cli_active_accounts} active in ${days}d`} />
        <Kpi icon={<Webhook className="size-4" />} label="Hook active" value={data.hook_active_accounts} sub={`${data.hook_cached_targets} cached targets`} />
        <Kpi icon={<TrendingUp className="size-4" />} label={`Revenue (${days}d)`} value={money(data.revenue_paise_in_window ?? 0)} sub={`${money(data.revenue_paise_total ?? 0)} all time`} />
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <Card title="Device authorizations" subtitle="CLI and hook logins that completed the device flow.">
          <Donut data={toPie(data.device_authorizations)} colors={PIE} height={180} />
          <Legend data={toPie(data.device_authorizations)} colors={PIE} />
        </Card>
        <Card title="Scan outcomes">
          <Donut data={toPie(data.scan_outcomes)} colors={[C.green, C.amber, C.red, C.grey]} height={180} />
          <Legend data={toPie(data.scan_outcomes)} colors={[C.green, C.amber, C.red, C.grey]} />
        </Card>
        <Card title="Checkouts" subtitle="“Created” means started but never completed.">
          <Donut data={toPie(data.payments_by_status)} colors={[C.grey, C.green, C.red]} height={180} />
          <Legend data={toPie(data.payments_by_status)} colors={[C.grey, C.green, C.red]} />
        </Card>
      </div>

      <p className="text-xs leading-relaxed text-muted-foreground">
        Installs themselves aren&apos;t observable here; npm and PyPI download counts live with those registries.
        What&apos;s measured is authentication and actual use, which is the stronger signal: an install that never
        authenticates never became a user.
      </p>
    </div>
  );
}

function maxPct(buckets: Record<string, UsageRow>): number {
  return Math.max(0, ...Object.values(buckets).map((b) => b?.pct ?? 0));
}

/** One bucket for one account: used / limit, with a proportional bar. */
function UsageCell({ row }: { row: UsageRow | undefined }) {
  if (!row) return <span className="text-muted-foreground">-</span>;

  const unlimited = row.limit_value === null;
  const pct = row.pct ?? 0;
  // State beats identity, same rule as the customer-facing meters.
  const colour = pct >= 100 ? "bg-severity-critical" : pct >= 80 ? "bg-severity-medium" : "bg-brand";

  return (
    <div className="min-w-24 space-y-1">
      <div className="flex items-baseline gap-1 text-[13px] tabular-nums">
        <span className={pct >= 100 ? "font-medium text-severity-critical" : ""}>{row.used}</span>
        <span className="text-muted-foreground">/ {unlimited ? "∞" : row.limit_value}</span>
        {row.is_override ? (
          <span
            className="ml-0.5 rounded border border-brand/40 bg-brand/10 px-1 text-[9px] text-brand-text"
            title="Admin override, not the plan default"
          >
            set
          </span>
        ) : null}
      </div>
      {!unlimited && row.limit_value! > 0 ? (
        <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
          <div className={`h-full rounded-full ${colour}`} style={{ width: `${Math.min(pct, 100)}%` }} />
        </div>
      ) : null}
    </div>
  );
}

function Kpi({
  icon,
  label,
  value,
  sub,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  sub?: string;
  tone?: "warn";
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-2 text-muted-foreground">
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <p className={`mt-2 truncate text-2xl font-semibold tracking-tight tabular-nums ${tone === "warn" ? "text-severity-medium" : ""}`}>
        {String(value ?? "-")}
      </p>
      {sub ? <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p> : null}
    </div>
  );
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4 rounded-xl border border-border bg-card p-5">
      <div>
        <h2 className="text-sm font-medium">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p> : null}
      </div>
      {children}
    </section>
  );
}

/** The chart's own numbers as text: colour is never the only carrier. */
function Legend({ data, colors }: { data: Array<{ name: string; value: number }>; colors: string[] }) {
  if (data.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5">
      {data.map((d, i) => (
        <li key={d.name} className="flex items-center gap-1.5 text-[12px]">
          <span className="size-2 rounded-full" style={{ background: colors[i % colors.length] }} aria-hidden="true" />
          <span className="text-muted-foreground capitalize">{d.name.replace(/_/g, " ")}</span>
          <span className="tabular-nums">{d.value}</span>
        </li>
      ))}
    </ul>
  );
}
