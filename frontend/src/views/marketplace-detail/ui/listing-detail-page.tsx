"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ExternalLink,
  Heart,
  Loader2,
  Scale,
  ShieldAlert,
} from "lucide-react";

import {
  GRADE_LABELS,
  GradeBadge,
  INSTALL_TARGET_LABELS,
  PRICE_LABELS,
  PopularitySignals,
  ScanStatePill,
  getListing,
  setFavorite,
  type InstallTarget,
  type ListingDetail,
} from "@/entities/marketplace";
import { ExplainButton } from "@/features/ai-explain";
import { ApiError } from "@/shared/api";
import { Badge } from "@/shared/ui/badge";
import { BrandIcon } from "@/shared/ui/brand-icon";
import { Button, buttonVariants } from "@/shared/ui/button";
import { EmptyState, Panel, PanelBody, PanelHeader, PanelTitle } from "@/shared/ui";

import { InstallDialog } from "./install-dialog";
import { ReportDialog } from "./report-dialog";
import { WhyThisGrade } from "./why-this-grade";

/**
 * One server, in full.
 *
 * The page is ordered by what someone deciding whether to install actually
 * needs, in the order they need it: what it is, how safe it is and why, where
 * it came from, what it can do, and only then how to install it.
 *
 * Popularity appears well below the grade and in muted type. That is not
 * aesthetic preference — putting a star count next to a letter invites the
 * reader to average them, and they do not average.
 */

export function ListingDetailPage({ slug }: { slug: string }) {
  const [listing, setListing] = useState<ListingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [favorited, setFavorited] = useState(false);
  const [installOpen, setInstallOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getListing(slug)
      .then((result) => {
        if (!cancelled) setListing(result);
      })
      .catch((error) => {
        if (cancelled) return;
        if (error instanceof ApiError && error.status === 404) setNotFound(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="size-5 animate-spin text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">Loading</span>
      </div>
    );
  }

  if (notFound || !listing) {
    return (
      <EmptyState
        title="Server not found"
        body="This listing does not exist, or it is private to another workspace."
        action={
          <Link href="/marketplace" className={buttonVariants({ variant: "outline" })}>
            Back to the marketplace
          </Link>
        }
      />
    );
  }

  const { security, popularity } = listing;
  const scannedVersion = listing.versions.find((v) => v.version === security.scannedVersion);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{listing.title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {listing.publisher ? `${listing.publisher} · ` : ""}
            {listing.latestVersion ? `v${listing.latestVersion}` : "version not stated"}
          </p>
          <p className="mt-3 max-w-2xl text-sm">{listing.description}</p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              const next = !favorited;
              setFavorited(next);
              void setFavorite(listing.id, next).catch(() => setFavorited(!next));
            }}
          >
            <Heart
              className={`size-4 ${favorited ? "fill-current text-severity-critical" : ""}`}
              aria-hidden="true"
            />
            {favorited ? "Saved" : "Save"}
          </Button>
          <Button onClick={() => setInstallOpen(true)} disabled={listing.installTargets.length === 0}>
            Install
          </Button>
        </div>
      </div>

      {/* Security first, and on its own, before anything that could dilute it. */}
      <Panel>
        <PanelHeader>
          <PanelTitle>Aevrin security scan</PanelTitle>
        </PanelHeader>
        <PanelBody className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <GradeBadge
              grade={security.grade}
              score={security.score}
              state={security.state}
              size="lg"
            />
            <ScanStatePill security={security} />
          </div>

          {security.state === "unscanned" ? (
            <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/40 p-4">
              <ShieldAlert
                className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                aria-hidden="true"
              />
              <p className="text-sm text-muted-foreground">
                This server has not been scanned. That is not a statement that it
                is safe — it means Aevrin has no evidence about it either way.
              </p>
            </div>
          ) : null}

          {security.state === "outdated" ? (
            <div className="flex items-start gap-3 rounded-lg border border-severity-medium/25 bg-severity-medium/10 p-4">
              <AlertTriangle
                className="mt-0.5 size-4 shrink-0 text-severity-medium"
                aria-hidden="true"
              />
              <p className="text-sm">
                The grade above was earned by{" "}
                <span className="font-medium">v{security.scannedVersion}</span>. The
                current release is{" "}
                <span className="font-medium">v{security.latestVersion}</span>, which has
                not been scanned. Do not read the grade as applying to it.
              </p>
            </div>
          ) : null}

          {/* Sub-scores. The whole point of showing three numbers is that
              "overall C" is unactionable and "MCP surface D, dependencies A"
              tells you where to look. */}
          {scannedVersion ? (
            <div className="grid gap-3 sm:grid-cols-3">
              <SubScore label="Code security" value={scannedVersion.codeScore} />
              <SubScore label="MCP security" value={scannedVersion.mcpScore} />
              <SubScore label="Dependencies" value={scannedVersion.dependencyScore} />
            </div>
          ) : null}

          {security.grade ? (
            <WhyThisGrade listing={listing} version={scannedVersion ?? null} />
          ) : null}

          <ExplainButton
            subjectType="trust_grade"
            subjectId={listing.id}
            label={
              security.grade
                ? `Why is this grade ${security.grade}?`
                : "Explain this server's security position"
            }
          />
        </PanelBody>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel className="lg:col-span-2">
          <PanelHeader>
            <PanelTitle>Source</PanelTitle>
          </PanelHeader>
          <PanelBody className="space-y-3 text-sm">
            <SourceRow
              label="Listed via"
              value={
                listing.source === "registry"
                  ? "Official MCP Registry"
                  : listing.source === "admin"
                    ? "Added by Aevrin"
                    : "Submitted by a user"
              }
              href={listing.registryUrl}
            />
            {listing.repositoryUrl ? (
              <SourceRow
                label="Repository"
                value={listing.repositoryUrl.replace("https://github.com/", "")}
                href={listing.repositoryUrl}
                icon={<BrandIcon name="github" className="size-3.5" />}
              />
            ) : null}
            {listing.homepageUrl ? (
              <SourceRow label="Homepage" value={listing.homepageUrl} href={listing.homepageUrl} />
            ) : null}
            <SourceRow
              label="Publisher licence"
              value={listing.license ?? "Not stated"}
              icon={<Scale className="size-3.5" aria-hidden="true" />}
            />
            <SourceRow label="Pricing" value={PRICE_LABELS[listing.priceType]} href={listing.pricingUrl} />
            {listing.githubLanguage ? (
              <SourceRow label="Language" value={listing.githubLanguage} />
            ) : null}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader>
            <PanelTitle>Popularity</PanelTitle>
          </PanelHeader>
          <PanelBody className="space-y-3">
            <PopularitySignals popularity={popularity} className="flex-col !items-start gap-2" />
            <p className="border-t border-border pt-3 text-xs text-muted-foreground">
              These count stars, forks and package downloads. None of them is a
              count of users, and none of them is a security signal.
            </p>
          </PanelBody>
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel>
          <PanelHeader>
            <PanelTitle>Compatibility</PanelTitle>
          </PanelHeader>
          <PanelBody>
            {listing.installTargets.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {listing.installTargets.map((target) => (
                  <Badge key={target} variant="secondary">
                    {INSTALL_TARGET_LABELS[target as InstallTarget] ?? target}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                This server declares no transport Aevrin recognises, so there is
                no install recipe to offer. Speaking MCP in principle is not the
                same as being installable here.
              </p>
            )}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader>
            <PanelTitle>Versions</PanelTitle>
          </PanelHeader>
          <PanelBody className="space-y-2">
            {listing.versions.length === 0 ? (
              <p className="text-sm text-muted-foreground">No versions recorded.</p>
            ) : (
              listing.versions.slice(0, 8).map((version) => (
                <div
                  key={version.id}
                  className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm"
                >
                  <span className="font-mono text-xs">v{version.version}</span>
                  {version.trustGrade ? (
                    <span className="text-xs text-muted-foreground">
                      {version.trustGrade} · {GRADE_LABELS[version.trustGrade]}
                      {version.securityScore !== null ? ` · ${version.securityScore}/100` : ""}
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">Not scanned</span>
                  )}
                </div>
              ))
            )}
          </PanelBody>
        </Panel>
      </div>

      {listing.events.length > 0 ? (
        <Panel>
          <PanelHeader>
            <PanelTitle>Timeline</PanelTitle>
          </PanelHeader>
          <PanelBody className="space-y-2">
            {listing.events.slice(0, 10).map((event) => (
              <div key={event.id} className="flex items-start gap-3 text-sm">
                <span
                  className={`mt-1.5 size-1.5 shrink-0 rounded-full ${
                    event.severity === "critical"
                      ? "bg-severity-critical"
                      : event.severity === "warning"
                        ? "bg-severity-medium"
                        : "bg-muted-foreground"
                  }`}
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p>
                    {formatEvent(event.eventType)}
                    {event.oldValue && event.newValue ? (
                      <span className="text-muted-foreground">
                        {" "}
                        — {event.oldValue} → {event.newValue}
                      </span>
                    ) : null}
                  </p>
                  {event.reason ? (
                    <p className="text-xs text-muted-foreground">{event.reason}</p>
                  ) : null}
                </div>
              </div>
            ))}
          </PanelBody>
        </Panel>
      ) : null}

      <div className="flex justify-end">
        <Button variant="ghost" size="sm" onClick={() => setReportOpen(true)}>
          Report this listing
        </Button>
      </div>

      <InstallDialog
        listing={listing}
        open={installOpen}
        onOpenChange={setInstallOpen}
      />
      <ReportDialog listing={listing} open={reportOpen} onOpenChange={setReportOpen} />
    </div>
  );
}

function SubScore({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded-lg border border-border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">
        {/* "Not assessed" rather than a confident 100. A category with no
            findings and a category that was never examined are different
            claims, and only one of them is good news. */}
        {value === null ? (
          <span className="text-sm font-normal text-muted-foreground">Not assessed</span>
        ) : (
          `${value}/100`
        )}
      </p>
    </div>
  );
}

function SourceRow({
  label,
  value,
  href,
  icon,
}: {
  label: string;
  value: string;
  href?: string | null;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="inline-flex min-w-0 items-center gap-1.5 truncate font-medium hover:underline"
        >
          {icon}
          <span className="truncate">{value}</span>
          <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
        </a>
      ) : (
        <span className="inline-flex items-center gap-1.5 truncate font-medium">
          {icon}
          {value}
        </span>
      )}
    </div>
  );
}

function formatEvent(type: string): string {
  return (
    {
      listing_added: "Added to the marketplace",
      listing_updated: "Metadata updated",
      version_added: "New version published",
      source_changed: "Source changed",
      scan_completed: "Security scan completed",
      grade_changed: "Trust grade changed",
      popularity_changed: "Popularity updated",
      admin_override: "Edited by an administrator",
      status_changed: "Status changed",
      report_actioned: "A report was actioned",
    }[type] ?? type.replace(/_/g, " ")
  );
}
