import { GitFork, Star, CircleDot, Download } from "lucide-react";

import type { ListingPopularity } from "../model/types";

/**
 * Popularity, labelled as exactly what each number measures.
 *
 * "GitHub stars", never "users". Stars are a count of people who clicked a
 * button on a web page; downloads include every CI run that ever installed
 * the package. Neither is a count of humans depending on this, and neither is
 * evidence about security.
 *
 * A null metric renders as nothing at all. It is not shown as `0`, because a
 * repository whose metadata could not be fetched has unknown stars, and
 * printing zero would be publishing a false claim about someone's project.
 */

export function PopularitySignals({
  popularity,
  className = "",
}: {
  popularity: ListingPopularity;
  className?: string;
}) {
  const signals = [
    { icon: Star, value: popularity.githubStars, label: "GitHub stars" },
    { icon: GitFork, value: popularity.githubForks, label: "GitHub forks" },
    { icon: CircleDot, value: popularity.githubOpenIssues, label: "Open issues" },
    {
      icon: Download,
      value: popularity.npmDownloadsLastMonth,
      label: "npm downloads, last month",
    },
  ].filter((s): s is typeof s & { value: number } => typeof s.value === "number");

  if (signals.length === 0) {
    return (
      <p className={`text-xs text-muted-foreground ${className}`}>
        Popularity metrics unavailable
      </p>
    );
  }

  return (
    <ul className={`flex flex-wrap items-center gap-x-4 gap-y-1.5 ${className}`}>
      {signals.map(({ icon: Icon, value, label }) => (
        <li
          key={label}
          className="flex items-center gap-1.5 text-xs text-muted-foreground"
          title={label}
        >
          <Icon className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="tabular-nums">{compact(value)}</span>
          <span className="sr-only">{label}</span>
        </li>
      ))}
    </ul>
  );
}

/** 25400 becomes 25.4k. */
function compact(value: number): string {
  if (value < 1000) return String(value);
  if (value < 1_000_000) return `${(value / 1000).toFixed(value < 10_000 ? 1 : 0)}k`;
  return `${(value / 1_000_000).toFixed(1)}m`;
}
