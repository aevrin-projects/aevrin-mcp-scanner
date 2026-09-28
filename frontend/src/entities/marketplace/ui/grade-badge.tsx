import { GRADE_LABELS, type ScanState, type TrustGrade } from "../model/types";

/**
 * The A-F letter, and the one component allowed to render it.
 *
 * It refuses to display a grade without its context. `state` is required, not
 * optional, so there is no way to call this and get a bare confident letter
 * for a scan that was partial, stale, or never ran. That constraint is the
 * entire point of the component: the failure mode this product cannot afford
 * is a green "A" sitting next to software nobody has actually looked at.
 */

const GRADE_STYLES: Record<TrustGrade, string> = {
  A: "bg-severity-low/12 text-severity-low border-severity-low/25",
  B: "bg-chart-1/12 text-chart-1 border-chart-1/25",
  C: "bg-severity-medium/12 text-severity-medium border-severity-medium/25",
  D: "bg-severity-high/12 text-severity-high border-severity-high/25",
  F: "bg-severity-critical/12 text-severity-critical border-severity-critical/25",
};

// An unscanned or stale grade is drawn in neutral tones whatever the letter
// says. Colour reads as a verdict, and there is no verdict to give.
const MUTED = "bg-muted text-muted-foreground border-border";

const STATE_NOTE: Record<ScanState, string> = {
  complete: "Aevrin security scan",
  outdated: "This grade covers an older version",
  partial: "Partial coverage. Do not treat as clean.",
  ungraded: "Scanned, not graded",
  unscanned: "Not yet scanned",
  not_applicable: "Not security-scanned",
};

// What to say when there is no letter. Three different facts, and collapsing
// them was the bug: "Not yet scanned" was shown for a server Aevrin had
// scanned but could not grade, which is a claim that it never looked.
const NO_GRADE: Record<"ungraded" | "unscanned" | "not_applicable", { title: string; note: string }> = {
  ungraded: {
    title: "Scanned, not graded",
    note: "The scan could not establish enough to grade this server. Unknown, not safe.",
  },
  unscanned: {
    title: "Not yet scanned",
    note: "No security evidence. Not a statement that this is safe.",
  },
  not_applicable: {
    title: "Not security-scanned",
    note: "Aevrin has no scanner for this kind of item. Curated by an administrator.",
  },
};

export function GradeBadge({
  grade,
  riskScore,
  state,
  size = "md",
  variant = "full",
}: {
  grade: TrustGrade | null;
  /** 0-100, higher is worse. Labelled "risk" wherever it is shown, because
   *  the same numeral used to mean the opposite. */
  riskScore?: number | null;
  state: ScanState;
  size?: "sm" | "md" | "lg";
  /**
   * `full` pairs the tile with its explanation, for a detail view that has
   * room for it. `tile` is the square alone, for a grid card where the
   * explanation would not fit -- see the note below on why that is a layout
   * requirement rather than a preference.
   */
  variant?: "full" | "tile";
}) {
  const dimensions = {
    sm: "size-8 text-sm",
    md: "size-12 text-lg",
    lg: "size-20 text-3xl",
  }[size];

  if (variant === "tile") {
    // Nothing to show, and deliberately nothing rather than a "?" placeholder:
    // on a card the caller states the scan state in its own footer, so a
    // second unexplained glyph beside the publisher's logo read as a broken
    // image rather than as "no evidence".
    if (!grade || state in NO_GRADE) return null;
    const style = state === "complete" ? GRADE_STYLES[grade] : MUTED;
    return (
      <div
        className={`grid ${dimensions} shrink-0 place-items-center rounded-lg border ${style} font-semibold tabular-nums`}
        // The letter alone is meaningless to a screen reader, and the colour
        // that qualifies it is meaningless to anyone not seeing it. Both are
        // carried in text here so the tile is never a colour-only signal.
        role="img"
        aria-label={`Trust grade ${grade}. ${STATE_NOTE[state]}`}
      >
        {grade}
      </div>
    );
  }

  if (!grade || state in NO_GRADE) {
    const words = NO_GRADE[state in NO_GRADE ? (state as keyof typeof NO_GRADE) : "unscanned"];
    return (
      <div className="flex items-center gap-3">
        <div
          className={`grid ${dimensions} shrink-0 place-items-center rounded-lg border ${MUTED} font-semibold`}
          aria-hidden="true"
        >
          ?
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium">{words.title}</p>
          <p className="text-xs text-muted-foreground">{words.note}</p>
        </div>
      </div>
    );
  }

  // A grade that does not describe the current release, or that came from a
  // scan which did not finish, keeps its letter but loses its colour.
  const trustworthy = state === "complete";
  const style = trustworthy ? GRADE_STYLES[grade] : MUTED;

  return (
    <div className="flex items-center gap-3">
      <div
        className={`grid ${dimensions} shrink-0 place-items-center rounded-lg border ${style} font-semibold tabular-nums`}
      >
        {grade}
      </div>
      <div className="min-w-0">
        <p className="text-sm font-medium">
          {GRADE_LABELS[grade]}
          {typeof riskScore === "number" ? (
            <span className="ml-1.5 font-normal text-muted-foreground tabular-nums">
              risk {riskScore}/100
            </span>
          ) : null}
        </p>
        <p className="text-xs text-muted-foreground">{STATE_NOTE[state]}</p>
      </div>
    </div>
  );
}
