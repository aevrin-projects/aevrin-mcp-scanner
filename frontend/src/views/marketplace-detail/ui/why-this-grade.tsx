"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

import type { ListingDetail, ListingVersion } from "@/entities/marketplace";

/**
 * "Why this grade?" answered from evidence, before anyone asks an AI.
 *
 * This panel exists so that the explanation of a grade does not depend on
 * having configured a provider. Everything here is derived from the scan
 * itself: the sub-scores, the coverage state, the version the grade belongs
 * to. The AI button beside it adds prose; it does not add facts, and it is
 * never the only way to find out why a letter is what it is.
 */

export function WhyThisGrade({
  listing,
  version,
}: {
  listing: ListingDetail;
  version: ListingVersion | null;
}) {
  const [open, setOpen] = useState(false);
  const { security } = listing;
  const reasons = buildReasons(listing, version);

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
        <div className="border-t border-border px-4 py-3">
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
          <p className="mt-3 border-t border-border pt-2.5 text-xs text-muted-foreground">
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

    // Lowest sub-score first: that is the one that decided the letter, and it
    // is what a reader should go and look at.
    const parts = [
      { label: "code security", value: version.codeScore },
      { label: "MCP surface", value: version.mcpScore },
      { label: "dependencies", value: version.dependencyScore },
    ].filter((p): p is { label: string; value: number } => p.value !== null);

    if (parts.length > 0) {
      const weakest = parts.reduce((a, b) => (a.value <= b.value ? a : b));
      reasons.push(
        `The weakest area is ${weakest.label}, at ${weakest.value}/100. That is the part carrying the overall letter.`,
      );
    }

    const unassessed = [
      { label: "Code security", value: version.codeScore },
      { label: "MCP surface", value: version.mcpScore },
      { label: "Dependencies", value: version.dependencyScore },
    ].filter((p) => p.value === null);
    if (unassessed.length > 0) {
      reasons.push(
        `${unassessed.map((p) => p.label).join(", ")} produced no findings in this scan. That is not the same as being clean if coverage was incomplete.`,
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
