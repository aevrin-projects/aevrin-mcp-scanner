import type { Grade } from "./types";

/**
 * The A-F scale, in one place so the scan report, the marketplace listing and
 * the agent inventory can never render the same letter differently.
 *
 * `null` is a real state, not a missing value: a scan whose MCP tools could
 * not be enumerated has no evidence to make a claim from, so it gets no
 * letter and no colour. Callers render it as "?" in neutral tones - never as
 * an absent field, which reads as still-loading, and never as an A.
 */
export const GRADE_LABELS: Record<Grade, string> = {
  A: "Trusted",
  B: "Generally safe",
  C: "Caution",
  D: "High risk",
  F: "Do not use",
};

/** Colour carries the verdict, so it tracks severity rather than the brand
 *  accent. Every use pairs it with the label above: a grade has to survive
 *  being read in greyscale. */
export const GRADE_STYLES: Record<Grade, string> = {
  A: "border-severity-low/30 bg-severity-low/10 text-severity-low",
  B: "border-chart-1/30 bg-chart-1/10 text-chart-1",
  C: "border-severity-medium/30 bg-severity-medium/10 text-severity-medium",
  D: "border-severity-high/30 bg-severity-high/10 text-severity-high",
  F: "border-severity-critical/30 bg-severity-critical/10 text-severity-critical",
};
