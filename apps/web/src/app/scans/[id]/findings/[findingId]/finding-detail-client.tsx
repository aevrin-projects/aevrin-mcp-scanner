"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, CheckCircle2, ExternalLink, Flag, RotateCcw, Wrench } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { Finding } from "@/lib/types";
import { OWASP_CATEGORY_LABELS } from "@/lib/types";
import { PageHeader, SectionCard } from "@/components/product-ui";
import { SeverityBadge } from "@/components/severity-badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { scoreImpactForSeverity, formatDateTime } from "@/lib/presentation";

export function FindingDetailClient({
  scanId,
  findingId,
  returnTo,
}: {
  scanId: string;
  findingId: string;
  returnTo?: string;
}) {
  const [finding, setFinding] = useState<Finding | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [triaging, setTriaging] = useState(false);
  const [triageReason, setTriageReason] = useState("");
  const [tier, setTier] = useState<"free" | "hobby" | "pro" | "team" | null>(null);
  const [fixing, setFixing] = useState(false);
  const [scanTargetType, setScanTargetType] = useState<string | null>(null);
  const [repoAccess, setRepoAccess] = useState<"loading" | "granted" | "not_granted" | "disconnected">("loading");
  const [fixBlocker, setFixBlocker] = useState<{ title: string; body: string; href: string; cta: string } | null>(null);

  // Fix It needs three things to be true:
  //   1. a Pro/Team plan,
  //   2. a finding from a GitHub *repository* scan — there is nothing to
  //      open a PR against for a live-server or pasted-config scan,
  //   3. that repository inside the GitHub App installation grant.
  //
  // The button is shown regardless and explains which one is missing when
  // clicked. Hiding it from accounts that can't use it yet makes the
  // feature undiscoverable to exactly the people who'd upgrade for it, and
  // silently absent UI reads as a bug rather than as a plan boundary.
  const isPaid = tier === "pro" || tier === "team";
  const isRepoScan = scanTargetType === "github_repo";
  const canUseFixIt = isPaid && isRepoScan && repoAccess === "granted";

  /** Null when Fix It is genuinely runnable; otherwise why it isn't yet. */
  function fixItBlocker(): { title: string; body: string; href: string; cta: string } | null {
    if (!isPaid) {
      return {
        title: "Fix It is on Pro and Team",
        body: "Aevrin drafts a patch, re-runs the scanner that raised this finding to confirm it clears, then opens a draft pull request.",
        href: "/pricing",
        cta: "See plans",
      };
    }
    if (!isRepoScan) {
      return {
        title: "Fix It needs a repository scan",
        body: `This finding came from a ${scanTargetType === "live_mcp_server" ? "live server" : "pasted config"} scan, so there is no source to open a pull request against. Scan the server's repository to use Fix It.`,
        href: "/scans/new",
        cta: "Scan a repository",
      };
    }
    if (repoAccess === "disconnected") {
      return {
        title: "Connect GitHub to use Fix It",
        body: "Aevrin needs write access to open a draft pull request on this repository.",
        href: "/settings/billing",
        cta: "Connect GitHub",
      };
    }
    if (repoAccess === "not_granted") {
      return {
        title: "This repository isn't in your GitHub grant",
        body: "Fix It can only open pull requests on repositories you granted Aevrin access to. You can add this one from GitHub at any time.",
        href: "/settings/billing",
        cta: "Manage access",
      };
    }
    return null;
  }

  useEffect(() => {
    api
      .getFinding(findingId)
      .then((loadedFinding) => {
        setFinding(loadedFinding);
        setTriageReason(loadedFinding.triage_reason ?? "");
      })
      .catch((err) => {
        const message = err instanceof ApiError ? err.message : "Could not load this finding.";
        setError(message);
      });
    api.getSubscription().then((sub) => setTier(sub.effective_tier)).catch(() => setTier("free"));
  }, [findingId]);

  // Resolve the scan's target, then whether that repo is inside the grant.
  useEffect(() => {
    if (!finding) return;
    let cancelled = false;
    api
      .getScan(String(finding.scan_id))
      .then(async (scan) => {
        if (cancelled) return;
        setScanTargetType(scan.target_type);
        if (scan.target_type !== "github_repo") {
          setRepoAccess("not_granted");
          return;
        }
        try {
          const { connected, repos } = await api.getGithubRepos();
          if (cancelled) return;
          if (!connected) {
            setRepoAccess("disconnected");
            return;
          }
          // Compare on owner/name so a trailing .git or slash can't cause a
          // false "not granted".
          const normalize = (value: string) =>
            value.replace(/^https?:\/\/github\.com\//i, "").replace(/\.git$/i, "").replace(/\/$/, "").toLowerCase();
          const target = normalize(scan.target);
          setRepoAccess(
            repos.some((repo) => repo.full_name.toLowerCase() === target) ? "granted" : "not_granted",
          );
        } catch {
          if (!cancelled) setRepoAccess("disconnected");
        }
      })
      .catch(() => {
        if (!cancelled) setRepoAccess("not_granted");
      });
    return () => {
      cancelled = true;
    };
  }, [finding]);

  async function runFixIt() {
    setFixing(true);
    try {
      const result = await api.fixFinding(findingId);
      if (result.status === "needs_github_connection" && result.install_url) {
        window.location.href = result.install_url;
        return;
      }
      const refreshed = await api.getFinding(findingId);
      setFinding(refreshed);
      if (result.status === "fixed") {
        toast.success("Fix It opened a draft pull request.");
      } else {
        toast.error(result.failure_reason ?? "Could not generate a fix for this finding.");
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not run Fix It.");
    } finally {
      setFixing(false);
    }
  }

  async function updateStatus(status: "open" | "fixed" | "false_positive", reason?: string) {
    setTriaging(true);
    try {
      const updated = await api.triageFinding(findingId, status, reason);
      setFinding(updated);
      setTriageReason(updated.triage_reason ?? "");
      toast.success(status === "open" ? "Finding reopened" : status === "fixed" ? "Marked as fixed" : "False positive recorded");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not update this finding.");
    } finally {
      setTriaging(false);
    }
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="size-4" />
        <AlertTitle>Could not load finding</AlertTitle>
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  if (!finding) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-20 rounded-xl" />
        <Skeleton className="h-80 rounded-xl" />
      </div>
    );
  }

  const location = finding.file_path
    ? `${finding.file_path}${finding.line_start ? `:${finding.line_start}` : ""}`
    : finding.manifest_field
      ? `${finding.tool_name_in_manifest ? `${finding.tool_name_in_manifest} -> ` : ""}${finding.manifest_field}`
      : "No file, line, or manifest field was recorded for this finding.";

  const scanHref = `/scans/${scanId}`;
  // Search params are already decoded by Next.js. Keep navigation on this
  // scan instead of accepting an arbitrary client-supplied URL.
  const backHref = returnTo === scanHref || returnTo?.startsWith(`${scanHref}?`) ? returnTo : scanHref;

  return (
    <div className="space-y-6">
      <Link
        href={backHref}
        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Back to filtered results
      </Link>

      <PageHeader
        title={finding.title}
        description="Review the recorded severity, category, source, context, remediation, and auditable triage history."
        actions={
          !finding.not_tested ? (
            <>
              {/* Fix It is the primary action on this page, so it sits in the
                  primary action slot. It was previously buried in a sidebar
                  card below triage — effectively undiscoverable. */}
              {!finding.excluded_path ? (
                finding.autofix_status === "fixed" && finding.autofix_pr_url ? (
                  <a
                    href={finding.autofix_pr_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={buttonVariants({ variant: "outline" })}
                  >
                    <ExternalLink className="size-4" />
                    View fix PR
                  </a>
                ) : (
                  <Button
                    disabled={fixing || repoAccess === "loading"}
                    variant={canUseFixIt ? "default" : "outline"}
                    onClick={() => {
                      const blocker = fixItBlocker();
                      if (blocker) {
                        setFixBlocker(blocker);
                        return;
                      }
                      void runFixIt();
                    }}
                  >
                    <Wrench className="size-4" />
                    {fixing ? "Generating fix…" : finding.autofix_status === "failed" ? "Retry Fix It" : "Fix It"}
                  </Button>
                )
              ) : null}
              {finding.triage_status === "open" ? (
                <Button variant="outline" disabled={triaging} onClick={() => void updateStatus("fixed")}>
                  <CheckCircle2 className="size-4" />
                  Mark as fixed
                </Button>
              ) : (
                <Button variant="outline" disabled={triaging} onClick={() => void updateStatus("open")}>
                  <RotateCcw className="size-4" />
                  Reopen finding
                </Button>
              )}
            </>
          ) : null
        }
      />

      {/* Shown only after someone actually asks for Fix It, so the page
          isn't permanently carrying an upsell banner — but the answer is
          specific about which precondition is missing, and links straight
          to fixing it. */}
      {fixBlocker ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-brand/30 bg-brand/[0.06] px-4 py-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground">{fixBlocker.title}</p>
            <p className="mt-1 text-sm text-muted-foreground">{fixBlocker.body}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setFixBlocker(null)}>
              Dismiss
            </Button>
            <Link href={fixBlocker.href} className={buttonVariants({ size: "sm" })}>
              {fixBlocker.cta}
            </Link>
          </div>
        </div>
      ) : null}

      {finding.autofix_status === "failed" && finding.autofix_failure_reason ? (
        <Alert>
          <AlertTriangle className="size-4" />
          <AlertTitle>Automatic fix didn&apos;t succeed</AlertTitle>
          <AlertDescription>{finding.autofix_failure_reason}</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.3fr)_360px]">
        <SectionCard
          title="Finding context"
          description="Everything shown below comes from the stored finding record for this scan."
        >
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              <SeverityBadge severity={finding.severity} />
              {finding.in_kev ? (
                <span className="rounded-full border border-red-500/40 bg-red-500/10 px-2 py-1 text-xs font-medium text-red-600 dark:text-red-400">
                  CISA KEV — confirmed exploited in the wild
                </span>
              ) : null}
              {finding.epss_score !== null ? (
                <span className="rounded-full border border-border px-2 py-1 text-xs text-muted-foreground">
                  EPSS {(finding.epss_score * 100).toFixed(finding.epss_score < 0.01 ? 2 : 0)}% exploitation probability (30d)
                </span>
              ) : null}
              <span className="rounded-full border border-border px-2 py-1 text-xs text-muted-foreground">
                {finding.triage_status.replace("_", " ")}
              </span>
              <span className="rounded-full border border-border px-2 py-1 text-xs text-muted-foreground">
                {OWASP_CATEGORY_LABELS[finding.owasp_category] ?? finding.owasp_category}
              </span>
              {finding.excluded_path ? (
                <span className="rounded-full border border-border px-2 py-1 text-xs text-muted-foreground">
                  Test/fixture path — excluded from score
                </span>
              ) : null}
            </div>
            {finding.original_severity && finding.original_severity !== finding.severity ? (
              <p className="text-xs text-muted-foreground">
                Downgraded from {finding.original_severity} based on {finding.in_kev ? "corroboration" : "low exploitation likelihood or scope"} — the tool&apos;s original severity is preserved here for audit.
              </p>
            ) : null}

            <div className="rounded-xl border border-border bg-background/80 p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Location</p>
              <p className="mt-2 break-all font-mono text-sm text-foreground">{location}</p>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <MetaPanel label="Scanner source" value={finding.tool} />
              <MetaPanel label="Recorded at" value={formatDateTime(finding.created_at)} />
              <MetaPanel label="Score impact" value={scoreImpactForSeverity(finding.severity)} />
              <MetaPanel label="Identifiers" value="Not available in the current backend response" />
            </div>

            <SectionBody title="Why it matters" body={finding.description} />
            <SectionBody title="Remediation" body={finding.remediation} />
          </div>
        </SectionCard>

        <div className="space-y-6">
          {finding.not_tested ? (
            <Alert>
              <AlertTriangle className="size-4" />
              <AlertTitle>Documented limitation</AlertTitle>
              <AlertDescription>
                This entry records a coverage limitation rather than an exploitable code finding, so remediation means performing the missing validation outside this static scan.
              </AlertDescription>
            </Alert>
          ) : null}

          <SectionCard title="Status" description="Triage changes are retained with their reason and timestamp.">
            <div className="space-y-4 text-sm leading-6 text-muted-foreground">
              <p>Current status: <strong className="text-foreground">{finding.triage_status.replace("_", " ")}</strong></p>
              {finding.triaged_at ? (
                <div className="rounded-xl border border-border bg-background/80 p-4">
                  <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Last triage</p>
                  <p className="mt-2 text-foreground">{formatDateTime(finding.triaged_at)}</p>
                  {finding.triage_reason ? <p className="mt-2 whitespace-pre-wrap">{finding.triage_reason}</p> : null}
                </div>
              ) : null}

              {!finding.not_tested ? (
                <div className="space-y-3 border-t border-border pt-4">
                  <div>
                    <label htmlFor="false-positive-reason" className="font-medium text-foreground">False-positive reason</label>
                    <p className="mt-1 text-xs">Explain why this result is not applicable or not exploitable. The reason is required and stored with the report.</p>
                  </div>
                  <Textarea
                    id="false-positive-reason"
                    value={triageReason}
                    onChange={(event) => setTriageReason(event.target.value)}
                    maxLength={1000}
                    rows={5}
                    placeholder="Example: This credential pattern is generated test data and cannot authenticate against any environment."
                  />
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <span className="text-xs">{triageReason.length} / 1000</span>
                    <Button
                      variant="outline"
                      disabled={triaging || triageReason.trim().length < 3}
                      onClick={() => void updateStatus("false_positive", triageReason.trim())}
                    >
                      <Flag className="size-4" />
                      {finding.triage_status === "false_positive" ? "Update report" : "Report false positive"}
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}

function MetaPanel({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-background/80 p-4">
      <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <p className="mt-2 text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}

function SectionBody({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-xl border border-border bg-background/80 p-4">
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{body}</p>
    </div>
  );
}
