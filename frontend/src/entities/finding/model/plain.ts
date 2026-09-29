import type { Severity, TriageStatus } from "./types";

/* Everyday words for a finding's severity and status. The scanner's own
 * values (critical, high, false_positive...) stay on the badges and under
 * Technical details; these say what they mean. */

/** "How serious is this problem?", one sentence per severity. */
export const SEVERITY_MEANINGS: Record<Severity, string> = {
  critical: "Very serious. Fix this before you use it.",
  high: "Serious. Fix this soon.",
  medium: "Worth fixing. It is not urgent on its own, but it adds to other problems.",
  low: "Small. Fix it when you can.",
  info: "Just so you know. It does not change the score.",
};

export const TRIAGE_LABELS: Record<TriageStatus, string> = {
  open: "Not fixed yet",
  fixed: "Fixed",
  false_positive: "Not a real problem",
};
