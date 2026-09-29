"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ExternalLink, Heart, Loader2, Scale } from "lucide-react";

import {
  INSTALL_TARGET_LABELS,
  PRICE_LABELS,
  ListingLogo,
  PopularitySignals,
  ScanWithAevrin,
  TypeBadge,
  ItemContentSections,
  RelatedSection,
  UseSection,
  getListing,
  setFavorite,
  type InstallTarget,
  type ListingDetail,
} from "@/entities/marketplace";
import { ApiError } from "@/shared/api";
import { formatDate } from "@/shared/lib/format";
import { Badge } from "@/shared/ui/badge";
import { BrandIcon } from "@/shared/ui/brand-icon";
import { Button, buttonVariants } from "@/shared/ui/button";
import { EmptyState, Panel, PanelBody, PanelHeader, PanelTitle } from "@/shared/ui";

import { InstallDialog } from "./install-dialog";
import { ReportDialog } from "./report-dialog";

/**
 * One registry item, in full: what it is, how to use it, what it contains,
 * where it came from.
 *
 * The registry is discovery only and states nothing about an item's
 * security. For an MCP server, "Scan with Aevrin" hands off to the scan page,
 * which runs the canonical scanner as the signed-in user's own scan.
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
        if (!cancelled) {
          setListing(result);
          setFavorited(result.favorited);
        }
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
        title="Not found"
        body="This item does not exist, is not published, or is private to another workspace."
        action={
          <Link href="/marketplace" className={buttonVariants({ variant: "outline" })}>
            Back to the registry
          </Link>
        }
      />
    );
  }

  const { popularity } = listing;
  const events = listing.events.filter((event) => !RETIRED_EVENTS.has(event.eventType));
  const isServer = listing.itemType === "mcp_server";
  const byline = [listing.author, listing.publisher].filter(Boolean).join(" · ");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-4">
          <ListingLogo listing={listing} className="size-12" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight">{listing.title}</h1>
              <TypeBadge type={listing.itemType} />
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {byline ? `${byline} · ` : ""}
              {listing.latestVersion ? `v${listing.latestVersion}` : "version not stated"}
            </p>
            <p className="mt-3 max-w-2xl text-sm">{listing.description}</p>
            {listing.technologies.length || listing.useCases.length ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {listing.technologies.map((technology) => (
                  <Badge key={technology} variant="secondary" className="text-[11px]">
                    {technology}
                  </Badge>
                ))}
                {listing.useCases.map((useCase) => (
                  <Badge key={useCase} variant="outline" className="text-[11px]">
                    {useCase}
                  </Badge>
                ))}
              </div>
            ) : null}
          </div>
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
          {isServer ? (
            <Button
              onClick={() => setInstallOpen(true)}
              disabled={Object.keys(listing.installConfigs).length === 0}
            >
              Install
            </Button>
          ) : null}
        </div>
      </div>

      {isServer ? <ScanWithAevrin listing={listing} /> : null}

      <UseSection listing={listing} />
      <ItemContentSections listing={listing} />
      <RelatedSection listing={listing} />

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
                    : "Suggested by a user"
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
            {isServer ? (
              <SourceRow label="Pricing" value={PRICE_LABELS[listing.priceType]} href={listing.pricingUrl} />
            ) : null}
            {listing.repositoryRef ? <SourceRow label="Ref" value={listing.repositoryRef} /> : null}
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

      {isServer ? (
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
                  <span className="text-xs text-muted-foreground">
                    {formatDate(version.firstSeenAt)}
                  </span>
                </div>
              ))
            )}
          </PanelBody>
        </Panel>
      </div>
      ) : null}

      {events.length > 0 ? (
        <Panel>
          <PanelHeader>
            <PanelTitle>Timeline</PanelTitle>
          </PanelHeader>
          <PanelBody className="space-y-2">
            {events.slice(0, 10).map((event) => (
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
                        {": "}
                        {event.oldValue} → {event.newValue}
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
          Report this item
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

// Timeline entries written when the registry still scanned. Historic rows may
// exist; they are hidden rather than rendered as a claim about a scan the
// registry no longer stands behind.
const RETIRED_EVENTS = new Set(["scan_completed", "grade_changed"]);

function formatEvent(type: string): string {
  return (
    {
      listing_added: "Added to the registry",
      listing_updated: "Metadata updated",
      version_added: "New version published",
      source_changed: "Source changed",
      popularity_changed: "Popularity updated",
      admin_override: "Edited by an administrator",
      status_changed: "Status changed",
      report_actioned: "A report was actioned",
    }[type] ?? type.replace(/_/g, " ")
  );
}
