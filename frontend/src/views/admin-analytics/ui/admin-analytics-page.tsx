"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Gauge, Globe, TerminalSquare, TrendingUp, Users, Webhook } from "lucide-react";
import { ApiError } from "@/shared/api";
import { cn } from "@/shared/lib/utils";
import { adminApi } from "@/entities/admin";
import { Alert, AlertDescription } from "@/shared/ui/alert";
import { Button } from "@/shared/ui/button";
import { PageHeader } from "@/shared/ui/page-header";
import { Panel } from "@/shared/ui/panel";
import { SectionCard } from "@/shared/ui/section-card";
import { Skeleton } from "@/shared/ui/skeleton";
import { TBody, TD, TH, THead, TR, Table } from "@/shared/ui/data-table";
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

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }
  if (!data || !usage) {
    return (
      <div className="flex flex-col gap-4" aria-busy>
        <Skeleton className="h-24 rounded-lg" />
        <Skeleton className="h-64 rounded-lg" />
        <Skeleton className="h-64 rounded-lg" />
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
    <>
      <PageHeader
        pretitle="Overview"
        title="Analytics"
        description="From Aevrin's own database: no third-party vendor, nothing about customers leaves your infrastructure."
        actions={RANGES.map((r) => (
          <Button
            key={r}
            size="sm"
            variant={days === r ? "default" : "outline"}
            aria-pressed={days === r}
            onClick={() => setDays(r)}
          >
            {r}d
          </Button>
        ))}
      />

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
      <SectionCard
        title="Usage by account"
        description="Against the limit actually enforced: an admin override wins over the plan default, and unlimited shows as ∞."
      >
        <div className="w-full overflow-x-auto" tabIndex={0}>
          <Table className="min-w-[860px]">
            <THead>
              <TR>
                <TH>Account</TH>
                <TH>Plan</TH>
                {BUCKETS.map((b) => (
                  <TH key={b}>{BUCKET_LABEL[b]}</TH>
                ))}
              </TR>
            </THead>
            <TBody>
              {accountRows.map(([userId, acct]) => (
                <TR key={userId}>
                  <TD>
                    <Link
                      href={`/admin/users/${userId}`}
                      className="font-medium underline-offset-4 hover:underline"
                    >
                      {acct.email}
                    </Link>
                    {acct.status !== "active" ? (
                      <span className="ml-2 text-xs text-severity-high capitalize">{acct.status}</span>
                    ) : null}
                  </TD>
                  <TD className="capitalize">{acct.tier}</TD>
                  {BUCKETS.map((b) => (
                    <TD key={b}>
                      <UsageCell row={acct.buckets[b]} />
                    </TD>
                  ))}
                </TR>
              ))}
            </TBody>
          </Table>
        </div>
        <p className="text-xs text-muted-foreground">
          Counted from Postgres rather than the live Redis counters, so this stays correct, and keeps working,
          when Redis is unavailable.
        </p>
      </SectionCard>

      {/* -------------------------------------------------------- traffic */}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <SectionCard title="Traffic" description="Pageviews and distinct daily visitors.">
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
        </SectionCard>

        <SectionCard title="Top pages">
          <RankedBars data={data.top_pages ?? []} labelKey="path" valueKey="views" color={C.brand} />
        </SectionCard>

        <SectionCard title="Referrers">
          <RankedBars data={data.top_referrers ?? []} labelKey="referrer" valueKey="views" color={C.blue} />
        </SectionCard>

        <SectionCard title="Devices">
          <Donut data={toPie(data.devices)} colors={PIE} />
          <Legend data={toPie(data.devices)} colors={PIE} />
        </SectionCard>
      </div>

      {/* ---------------------------------------------------------- usage */}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <SectionCard title="Scans per day">
          <TrendChart data={byDay(data.scans_by_day, "count")} xKey="day" series={[{ key: "count", label: "Scans", color: C.green }]} />
        </SectionCard>
        <SectionCard title="By surface" description="Which product surface started each scan.">
          <Donut data={toPie(data.scans_by_source)} colors={PIE} />
          <Legend data={toPie(data.scans_by_source)} colors={PIE} />
        </SectionCard>
        <SectionCard title="Signups per day">
          <TrendChart data={byDay(data.signups_by_day, "count")} xKey="day" series={[{ key: "count", label: "Signups", color: C.brand }]} />
        </SectionCard>
        <SectionCard title="Plans" description="Effective tier: a lapsed paid account counts as Free.">
          <Donut data={toPie(data.plan_distribution)} colors={PIE} />
          <Legend data={toPie(data.plan_distribution)} colors={PIE} />
        </SectionCard>
      </div>

      {/* ------------------------------------------------- CLI + hook + $ */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Kpi icon={<TerminalSquare className="size-4" />} label="CLI authenticated" value={data.cli_authenticated_accounts} sub={`${data.cli_active_accounts} active in ${days}d`} />
        <Kpi icon={<Webhook className="size-4" />} label="Hook active" value={data.hook_active_accounts} sub={`${data.hook_cached_targets} cached targets`} />
        <Kpi icon={<TrendingUp className="size-4" />} label={`Revenue (${days}d)`} value={money(data.revenue_paise_in_window ?? 0)} sub={`${money(data.revenue_paise_total ?? 0)} all time`} />
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <SectionCard title="Device authorizations" description="CLI and hook logins that completed the device flow.">
          <Donut data={toPie(data.device_authorizations)} colors={PIE} height={180} />
          <Legend data={toPie(data.device_authorizations)} colors={PIE} />
        </SectionCard>
        <SectionCard title="Scan outcomes">
          <Donut data={toPie(data.scan_outcomes)} colors={[C.green, C.amber, C.red, C.grey]} height={180} />
          <Legend data={toPie(data.scan_outcomes)} colors={[C.green, C.amber, C.red, C.grey]} />
        </SectionCard>
        <SectionCard title="Checkouts" description="“Created” means started but never completed.">
          <Donut data={toPie(data.payments_by_status)} colors={[C.grey, C.green, C.red]} height={180} />
          <Legend data={toPie(data.payments_by_status)} colors={[C.grey, C.green, C.red]} />
        </SectionCard>
      </div>

      <p className="text-xs leading-relaxed text-muted-foreground">
        Installs themselves aren&apos;t observable here; npm and PyPI download counts live with those registries.
        What&apos;s measured is authentication and actual use, which is the stronger signal: an install that never
        authenticates never became a user.
      </p>
    </>
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
  // Built on the shared Panel rather than its own bordered div: this used to
  // re-declare the card surface, so a change to the product's card styling
  // reached every screen except this one.
  return (
    <Panel className="gap-1 px-4 py-3.5">
      <div className="flex items-center gap-2 text-muted-foreground">
        {icon}
        <span className="subheader">{label}</span>
      </div>
      <p
        className={cn(
          "truncate text-2xl leading-8 font-semibold tracking-tight tabular-nums",
          tone === "warn" && "text-severity-medium",
        )}
      >
        {String(value ?? "—")}
      </p>
      {sub ? <p className="text-xs text-muted-foreground">{sub}</p> : null}
    </Panel>
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
