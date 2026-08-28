"use client";

import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { Activity, CheckCircle2, Clock3, Gauge, Server, WifiOff } from "lucide-react";

import { SiteFooter } from "@/widgets/site-footer";
import { Badge } from "@/shared/ui/badge";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/ui/card";
import { Metric } from "@/shared/ui/metric";

// Optional: DefectDojo is a best-effort push target, so when this is unset
// the status page simply does not claim anything about it rather than
// reporting a component nobody deployed as down.
const DEFECTDOJO_URL = process.env.NEXT_PUBLIC_DEFECTDOJO_URL;

/**
 * Two sources, deliberately kept distinct on the page:
 *
 * - **Now**: live checks run from the visitor's own browser. This is a static
 *   export with no server to run them from, and a check from the visitor's
 *   own network is the more honest signal anyway (fewer false "up" reports
 *   from a path only Cloudflare's edge can reach). See DECISIONS.md ADR-011.
 * - **History**: `GET /status/history`, recorded hourly by a scheduled job.
 *
 * The history's central caveat is carried through to the UI rather than
 * smoothed over: the recording job calls the API, so an API outage writes
 * nothing at all instead of writing a failure. A day with no checks is
 * therefore `no_data` -- rendered as a distinct neutral bar and excluded from
 * the uptime figure -- never as a passing day. The uptime percentage is
 * labelled "of N recorded checks" for the same reason: it is a real number
 * about real samples, not a coverage guarantee.
 */

type ServiceState = "operational" | "down" | "checking";

type LiveService = {
  id: string;
  name: string;
  description: string;
  group: string;
  state: ServiceState;
  latencyMs: number | null;
};

type HistoryDay = {
  date: string;
  status: "operational" | "degraded" | "down" | "no_data";
  checks: number;
  ok: number;
  uptime: number | null;
};

type HistoryService = {
  id: string;
  days: HistoryDay[];
  uptime: number | null;
  checks_recorded: number;
  days_with_data: number;
};

const STATE_CONFIG: Record<
  ServiceState,
  { label: string; icon: typeof CheckCircle2; badge: string }
> = {
  operational: {
    label: "Operational",
    icon: CheckCircle2,
    badge: "border-brand/25 bg-brand/10 text-brand-text",
  },
  down: {
    label: "Not reachable",
    icon: WifiOff,
    badge: "border-severity-critical/25 bg-severity-critical/10 text-severity-critical",
  },
  checking: {
    label: "Checking",
    icon: Activity,
    badge: "border-border bg-muted text-muted-foreground",
  },
};

// A no_data bar is visually distinct from every real outcome on purpose: it
// is the one value that means "we do not know", and letting it read as a
// quiet success is the failure this whole feature is built to avoid.
const DAY_BAR: Record<HistoryDay["status"], { className: string; label: string }> = {
  operational: { className: "bg-brand", label: "All checks passed" },
  degraded: { className: "bg-severity-medium", label: "Some checks failed" },
  down: { className: "bg-severity-critical", label: "All checks failed" },
  no_data: { className: "bg-border", label: "No checks recorded" },
};

type Probe = { ok: boolean; ms: number | null };

/** A check plus the round-trip time it took, so latency is measured rather
 *  than asserted. A failed request has no meaningful timing, so it reports
 *  null instead of the time spent failing. */
async function probe(url: string, headers?: HeadersInit): Promise<Probe> {
  const started = performance.now();
  try {
    const res = await fetch(url, {
      headers,
      signal: AbortSignal.timeout(5000),
      cache: "no-store",
    });
    return { ok: res.ok, ms: res.ok ? Math.round(performance.now() - started) : null };
  } catch {
    return { ok: false, ms: null };
  }
}

/** This document's own transfer time, from the Navigation Timing API. The
 *  page rendered, so Web is up by definition; this makes that claim carry a
 *  real measurement rather than a bare assertion. */
function documentLatency(): number | null {
  try {
    const [nav] = performance.getEntriesByType("navigation") as PerformanceNavigationTiming[];
    if (!nav?.responseEnd || !nav.requestStart) return null;
    return Math.round(nav.responseEnd - nav.requestStart);
  } catch {
    return null;
  }
}

const PENDING: LiveService[] = [
  { id: "web", name: "Web", description: "Marketing site and documentation.", group: "Platform", state: "checking", latencyMs: null },
  { id: "api", name: "API", description: "Scan orchestration, marketplace, and billing.", group: "Platform", state: "checking", latencyMs: null },
  { id: "auth", name: "Authentication", description: "Sign-in, sessions, and CLI device pairing.", group: "Identity", state: "checking", latencyMs: null },
];

export function StatusPage() {
  const [services, setServices] = useState<LiveService[]>(PENDING);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [history, setHistory] = useState<HistoryService[] | null>(null);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    let cancelled = false;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL!;
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
    const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!;

    Promise.all([
      probe(`${apiUrl}/health`),
      probe(`${supabaseUrl}/auth/v1/health`, { apikey: supabaseKey }),
      DEFECTDOJO_URL ? probe(`${DEFECTDOJO_URL}/login`) : Promise.resolve(null),
    ]).then(([api, auth, defectDojo]) => {
      if (cancelled) return;
      setServices([
        { ...PENDING[0], state: "operational", latencyMs: documentLatency() },
        { ...PENDING[1], state: api.ok ? "operational" : "down", latencyMs: api.ms },
        { ...PENDING[2], state: auth.ok ? "operational" : "down", latencyMs: auth.ms },
        ...(defectDojo === null
          ? []
          : [
              {
                id: "defectdojo",
                name: "OWASP-mapped reporting workspace",
                description: "DefectDojo instance findings are pushed to.",
                group: "Security",
                state: (defectDojo.ok ? "operational" : "down") as ServiceState,
                latencyMs: defectDojo.ms,
              },
            ]),
      ]);
      setCheckedAt(new Date());
    });

    // Independent of the live checks: the history is still worth showing when
    // the API is unreachable right now, and an unreachable API is exactly when
    // someone wants to see whether this has been happening.
    fetch(`${apiUrl}/status/history?days=30`, { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled) setHistory(data?.services ?? []);
      })
      .catch(() => {
        if (!cancelled) setHistory([]);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const settled = checkedAt !== null;
  const operational = services.filter((s) => s.state === "operational").length;
  const anyDown = services.some((s) => s.state === "down");
  const byId = new Map((history ?? []).map((h) => [h.id, h]));
  const anyHistory = (history ?? []).some((h) => h.checks_recorded > 0);

  // Across every service, of recorded checks only.
  const totalChecks = (history ?? []).reduce((n, h) => n + h.checks_recorded, 0);
  const totalOk = (history ?? []).reduce(
    (n, h) => n + h.days.reduce((m, d) => m + d.ok, 0),
    0,
  );
  const overallUptime = totalChecks > 0 ? (totalOk / totalChecks) * 100 : null;

  const overall = !settled ? "checking" : anyDown ? "down" : "operational";
  const overallConfig = STATE_CONFIG[overall];
  const OverallIcon = overallConfig.icon;
  const overallSummary = !settled
    ? "Running checks"
    : anyDown
      ? "Some systems are not reachable"
      : "All systems operational";

  return (
    <div>
      <div className="mx-auto max-w-4xl px-6 py-16">
        <section className="w-full space-y-4">
          <Card>
            <CardHeader className="gap-4 sm:grid-cols-[1fr_auto]">
              <div>
                <CardTitle className="text-2xl">Status</CardTitle>
                <CardDescription className="mt-1 text-sm">
                  Live checks run from your own browser, with the availability Aevrin has recorded
                  over the last 30 days.
                </CardDescription>
              </div>
              <CardAction className="static col-auto row-auto justify-self-start sm:justify-self-end">
                <Badge variant="outline" className={`h-7 gap-1.5 px-3 ${overallConfig.badge}`}>
                  <OverallIcon className="size-3.5" aria-hidden="true" />
                  {overallSummary}
                </Badge>
              </CardAction>
            </CardHeader>

            <CardContent className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-3">
                <Metric label="Services tracked" value={services.length} />
                <Metric
                  label="Operational now"
                  value={settled ? operational : "-"}
                  suffix={settled ? `/ ${services.length}` : undefined}
                  tone={settled && !anyDown ? "success" : anyDown ? "critical" : "default"}
                />
                <Metric
                  label="30 day uptime"
                  value={overallUptime !== null ? overallUptime.toFixed(2) : "-"}
                  suffix={overallUptime !== null ? "%" : undefined}
                  detail={
                    totalChecks > 0
                      ? `Of ${totalChecks.toLocaleString()} recorded checks`
                      : "No checks recorded yet"
                  }
                  tone={overallUptime !== null && overallUptime >= 99.9 ? "success" : "default"}
                />
              </div>

              <div className="flex flex-col gap-2 border-t border-border pt-4 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
                <span className="inline-flex items-center gap-1.5">
                  <Clock3 className="size-3.5" aria-hidden="true" />
                  {checkedAt
                    ? `Checked ${new Intl.DateTimeFormat("en-US", {
                        dateStyle: "medium",
                        timeStyle: "long",
                        timeZone: "UTC",
                      }).format(checkedAt)}`
                    : "Checking now"}
                </span>
                <span>Reload to run the checks again.</span>
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-3">
            {services.map((service, index) => {
              const config = STATE_CONFIG[service.state];
              const StatusIcon = config.icon;
              const record = byId.get(service.id);

              return (
                <motion.div
                  key={service.id}
                  initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.18, delay: index * 0.03 }}
                >
                  <Card>
                    <CardHeader className="gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
                      <div className="min-w-0">
                        <div className="flex min-w-0 flex-wrap items-center gap-2">
                          <CardTitle className="text-base">{service.name}</CardTitle>
                          <Badge variant="outline" className={`gap-1.5 ${config.badge}`}>
                            <StatusIcon className="size-3" aria-hidden="true" />
                            {config.label}
                          </Badge>
                          <Badge variant="secondary" className="gap-1.5">
                            <Server className="size-3" aria-hidden="true" />
                            {service.group}
                          </Badge>
                        </div>
                        <CardDescription className="mt-1">{service.description}</CardDescription>
                      </div>
                      <CardAction className="static col-auto row-auto justify-self-start sm:justify-self-end">
                        <div className="text-left sm:text-right">
                          <div className="inline-flex items-baseline gap-1 text-2xl font-semibold tabular-nums">
                            {record?.uptime !== null && record?.uptime !== undefined ? (
                              <>
                                {record.uptime.toFixed(2)}
                                <span className="text-sm font-normal text-muted-foreground">%</span>
                              </>
                            ) : service.latencyMs !== null ? (
                              <>
                                {service.latencyMs}
                                <span className="text-sm font-normal text-muted-foreground">ms</span>
                              </>
                            ) : (
                              <span className="text-muted-foreground">-</span>
                            )}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {record && record.checks_recorded > 0
                              ? `${record.checks_recorded.toLocaleString()} checks recorded`
                              : service.latencyMs !== null
                                ? "This check"
                                : "No timing"}
                          </div>
                        </div>
                      </CardAction>
                    </CardHeader>

                    {record && record.days.length > 0 ? (
                      <CardContent className="space-y-2">
                        <div
                          className="flex h-10 items-stretch gap-[3px] overflow-hidden rounded-lg bg-muted/30 p-1.5"
                          role="img"
                          aria-label={
                            record.checks_recorded > 0
                              ? `30 day availability for ${service.name}: ${record.uptime?.toFixed(2)} percent of ${record.checks_recorded} recorded checks passed, across ${record.days_with_data} days with data.`
                              : `No availability recorded for ${service.name}.`
                          }
                        >
                          {record.days.map((day) => {
                            const bar = DAY_BAR[day.status];
                            return (
                              <span
                                key={day.date}
                                className={`min-w-[2px] flex-1 rounded-[2px] ${bar.className}`}
                                // Native title rather than a tooltip component:
                                // there is no Tooltip in this app's design
                                // system, and adding one for a hover hint on a
                                // static page is not worth the dependency.
                                title={`${day.date}: ${bar.label}${
                                  day.checks > 0 ? ` (${day.ok}/${day.checks})` : ""
                                }`}
                              />
                            );
                          })}
                        </div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>30 days ago</span>
                          {record.days_with_data < record.days.length ? (
                            <span>
                              {record.days.length - record.days_with_data} days without checks
                            </span>
                          ) : null}
                          <span>Today</span>
                        </div>
                      </CardContent>
                    ) : null}
                  </Card>
                </motion.div>
              );
            })}
          </div>

          {/* Stated, not omitted. Before the first scheduled run there is
              genuinely nothing recorded, and saying so is more useful than an
              empty strip that looks like a rendering fault. */}
          {history !== null && !anyHistory ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Availability history</CardTitle>
                <CardDescription>Nothing recorded yet.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/20 p-4">
                  <Gauge className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <p className="text-sm leading-6 text-muted-foreground">
                    Availability is sampled hourly and kept for 30 days, but no samples have been
                    recorded yet. Until they have, the checks above are a single measurement taken
                    when this page loaded. An uptime figure will appear here once there is data
                    behind it, rather than being estimated in the meantime.
                  </p>
                </div>
              </CardContent>
            </Card>
          ) : null}

          {anyHistory ? (
            <p className="px-1 text-xs leading-5 text-muted-foreground">
              Uptime covers the checks actually recorded, sampled hourly and kept for 30 days. A day
              with no checks is shown as a neutral bar and left out of the percentage: the recording
              job reaches Aevrin over the network, so an outage leaves a gap rather than a failed
              sample, and counting gaps as successes would report an outage as a perfect score.
            </p>
          ) : null}
        </section>
      </div>
      <SiteFooter />
    </div>
  );
}
