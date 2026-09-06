"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { SeverityBadge, type Severity } from "@/entities/finding";
import type { ListingDetail, ListingVersion } from "@/entities/marketplace";

/**
 * "Why this grade?" answered from evidence, before anyone asks an AI.
 *
 * This panel exists so that the explanation of a grade does not depend on
 * having configured a provider. Everything here is derived from the scan
 * itself: the findings that earned the letter, the coverage state, the
 * version the grade belongs to. The AI button beside it adds prose; it does
 * not add facts, and it is never the only way to find out why a letter is
 * what it is.
 *
 * The finding evidence leads and the contextual reasons follow. Listing only
 * the context - stdio transport, secret variables, an outdated scan - read as
 * if those were what earned the letter, when they are properties of the
 * server that the grade does not come from. The severity counts and the
 * rules that fired are what the grade is actually computed on, so they go
 * first and are labelled as such.
 */

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];

export function WhyThisGrade({
  listing,
  version,
}: {
  listing: ListingDetail;
  version: ListingVersion | null;
}) {
  const [open, setOpen] = useState(false);
  const { security, gradeRationale } = listing;
  const reasons = buildReasons(listing, version);
  const counted = SEVERITY_ORDER.filter(
    (severity) => (gradeRationale?.severityCounts?.[severity] ?? 0) > 0,
  );

  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm font-medium"
        aria-expanded={open}
      >
        Why grade {security.grade}?
        <ChevronDown
          className={`size-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      {open ? (
        <div className="space-y-4 border-t border-border px-4 py-3">
          {gradeRationale ? (
            <div className="space-y-3">
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                Findings this grade was computed from
              </p>

              {counted.length > 0 ? (
                <ul className="flex flex-wrap items-center gap-2">
                  {counted.map((severity) => (
                    <li key={severity} className="flex items-center gap-1.5 text-sm">
                      <span className="tabular-nums font-medium">
                        {gradeRationale.severityCounts[severity]}
                      </span>
                      <SeverityBadge severity={severity} />
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No finding above informational was recorded. The letter reflects what the
                  scan could read, not a guarantee.
                </p>
              )}

              {gradeRationale.drivers.length > 0 ? (
                <ul className="divide-y divide-border rounded-md border border-border">
                  {gradeRationale.drivers.map((driver) => (
                    <li
                      key={driver.ruleId}
                      className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
                    >
                      <span className="min-w-0">
                        <span className="block truncate">{driver.label}</span>
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {driver.ruleId} · {driver.occurrences}{" "}
                          {driver.occurrences === 1 ? "tool" : "tools"}
                        </span>
                      </span>
                      <SeverityBadge severity={driver.severity} className="shrink-0" />
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          <div className="space-y-2">
            {gradeRationale ? (
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                Context
              </p>
            ) : null}
            <ul className="space-y-2 text-sm">
              {reasons.map((reason) => (
                <li key={reason} className="flex gap-2.5">
                  <span
                    className="mt-1.5 size-1.5 shrink-0 rounded-full bg-muted-foreground"
                    aria-hidden="true"
                  />
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          </div>

          <p className="border-t border-border pt-2.5 text-xs text-muted-foreground">
            Grades are computed from scanner findings, coverage, and the
            capabilities a server declares. The same inputs always produce the
            same letter.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function buildReasons(listing: ListingDetail, version: ListingVersion | null): string[] {
  const reasons: string[] = [];
  const { security } = listing;

  if (version) {
    reasons.push(
      `The grade was computed from a scan of v${version.version}${
        version.scannedAt ? ` on ${new Date(version.scannedAt).toLocaleDateString()}` : ""
      }.`,
    );

    if (version.riskScore !== null) {
      reasons.push(
        `Its risk score was ${version.riskScore} out of 100, where 0 is clean and 100 is "do not use".`,
      );
    }
  }

  if (security.coverageComplete === false) {
    reasons.push(
      "Scan coverage was incomplete: at least one scanner stage did not run. Unknown categories count against the grade rather than for it.",
    );
  }

  if (security.state === "outdated") {
    reasons.push(
      `This grade does not cover v${security.latestVersion}. A new release has not been scanned yet.`,
    );
  }

  if (listing.installation?.packages?.some((p) => p.transport === "stdio")) {
    reasons.push(
      "This server runs as a local process on the machine that installs it, which is a broader capability than a remote endpoint.",
    );
  }

  const secretVariables =
    listing.installation?.packages?.flatMap((p) =>
      (p.environment ?? []).filter((v) => v.secret).map((v) => v.name),
    ) ?? [];
  if (secretVariables.length > 0) {
    reasons.push(
      `It asks for ${secretVariables.length} secret value${secretVariables.length > 1 ? "s" : ""} (${secretVariables.slice(0, 3).join(", ")}), so it holds credentials for the systems it reaches.`,
    );
  }

  if (reasons.length === 0) {
    reasons.push("No risk factors were recorded for this scan.");
  }

  return reasons;
}
