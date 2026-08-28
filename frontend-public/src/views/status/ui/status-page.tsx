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
 * Live checks, run from the visitor's own browser rather than the server:
 * this is a static export with no server to run them from, and a check from
 * the actual visitor's network is arguably the more honest signal anyway
 * (fewer false "up" reports from a healthy path that only Cloudflare's edge
 * can reach). See DECISIONS.md ADR-011.
 *
 * What this page deliberately does NOT show, and why it matters here more
 * than on most status pages: a 30-day uptime percentage, a per-day history
 * strip, and an incident timeline. Aevrin runs no uptime monitoring and
 * stores no availability history, so every one of those numbers would have
 * to be invented. On a security vendor's own status page that is the single
 * most damaging inaccuracy available, and it is the same rule the product
 * applies to itself everywhere else: an unscanned listing scores zero rather
 * than a neutral default, a grade never outlives the version it describes.
 * The "Availability history" panel below states the absence plainly instead.
 */

type ServiceState = "operational" | "down" | "checking";

type Service = {
  id: string;
  name: string;
  description: string;
  group: string;
  state: ServiceState;
  /** Round-trip time actually measured for this check, in ms. */
  latencyMs: number | null;
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
    if (!nav || !nav.responseEnd || !nav.requestStart) return null;
    return Math.round(nav.responseEnd - nav.requestStart);
  } catch {
    return null;
  }
}

const PENDING: Service[] = [
  { id: "web", name: "Web", description: "Marketing site and documentation.", group: "Platform", state: "checking", latencyMs: null },
  { id: "api", name: "API", description: "Scan orchestration, marketplace, and billing.", group: "Platform", state: "checking", latencyMs: null },
  { id: "auth", name: "Authentication", description: "Sign-in, sessions, and CLI device pairing.", group: "Identity", state: "checking", latencyMs: null },
];

export function StatusPage() {
  const [services, setServices] = useState<Service[]>(PENDING);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
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
        {
          ...PENDING[0],
          state: "operational",
          latencyMs: documentLatency(),
        },
        { ...PENDING[1], state: api.ok ? "operational" : "down", latencyMs: api.ms },
        { ...PENDING[2], state: auth.ok ? "operational" : "down", latencyMs: auth.ms },
        // Listed only when it is actually deployed. Reporting a component
        // nobody configured as "down" would make a healthy system look
        // degraded.
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

    return () => {
      cancelled = true;
    };
  }, []);

  const settled = checkedAt !== null;
  const operational = services.filter((s) => s.state === "operational").length;
  const anyDown = services.some((s) => s.state === "down");
  const measured = services.map((s) => s.latencyMs).filter((ms): ms is number => ms !== null);
  const slowest = measured.length > 0 ? Math.max(...measured) : null;

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
                  Live endpoint checks for Aevrin&apos;s public services, run from your own browser.
                </CardDescription>
              </div>
              <CardAction className="static col-auto row-auto justify-self-start sm:justify-self-end">
                <Badge
                  variant="outline"
                  className={`h-7 gap-1.5 px-3 ${overallConfig.badge}`}
                >
                  <OverallIcon className="size-3.5" aria-hidden="true" />
                  {overallSummary}
                </Badge>
              </CardAction>
            </CardHeader>

            <CardContent className="space-y-4">
              {/* Every figure here is counted or measured on this page load.
                  None of them is a stored or historical value. */}
              <div className="grid gap-4 sm:grid-cols-3">
                <Metric label="Services tracked" value={services.length} />
                <Metric
                  label="Operational now"
                  value={settled ? operational : "-"}
                  suffix={settled ? `/ ${services.length}` : undefined}
                  tone={settled && !anyDown ? "success" : anyDown ? "critical" : "default"}
                />
                <Metric
                  label="Slowest response"
                  value={slowest ?? "-"}
                  suffix={slowest !== null ? "ms" : undefined}
                  detail="Measured from your browser"
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
                            {service.latencyMs !== null ? (
                              <>
                                {service.latencyMs}
                                <span className="text-sm font-normal text-muted-foreground">ms</span>
                              </>
                            ) : (
                              <span className="text-muted-foreground">-</span>
                            )}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {service.latencyMs !== null ? "This check" : "No timing"}
                          </div>
                        </div>
                      </CardAction>
                    </CardHeader>
                  </Card>
                </motion.div>
              );
            })}
          </div>

          {/* Stated, not omitted. Silently dropping the history section would
              read as "nothing to report"; the absence of monitoring is itself
              the thing a reader needs to know when judging this page. */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Availability history</CardTitle>
              <CardDescription>Not recorded.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/20 p-4">
                <Gauge className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <p className="text-sm leading-6 text-muted-foreground">
                  Aevrin does not currently run uptime monitoring or store availability history, so
                  there is no 30-day uptime figure, per-day history, or incident timeline to show.
                  The checks above are a single measurement taken when this page loaded, and they are
                  not retained. Publishing an uptime percentage without monitoring behind it would be
                  a claim with no evidence for it, which is the one thing a security product&apos;s
                  own status page must not do.
                </p>
              </div>
            </CardContent>
          </Card>
        </section>
      </div>
      <SiteFooter />
    </div>
  );
}
