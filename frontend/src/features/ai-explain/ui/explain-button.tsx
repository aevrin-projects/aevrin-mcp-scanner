"use client";

import { useState } from "react";
import { Loader2, Sparkles } from "lucide-react";

import {
  explain,
  type ExplainSubject,
  type ExplanationResult,
} from "@/entities/ai-provider";
import { ApiError } from "@/shared/api";
import { Button } from "@/shared/ui/button";

/**
 * "Explain with AI", and the panel it opens.
 *
 * Two rules govern everything this component renders.
 *
 * **An explanation is never presented as a finding.** The panel is visually
 * distinct, it is labelled "AI explanation", and it carries the provider and
 * model that produced it. A reader must always be able to tell the difference
 * between something Aevrin's scanners established and something a language
 * model said about it.
 *
 * **A failure here is not a failure of the page.** When no provider is
 * configured, or a vendor is down, this renders a quiet line of text next to a
 * finding that remains completely valid. It never throws, never shows an error
 * banner, and never suggests the security result is in doubt.
 */

export function ExplainButton({
  subjectType,
  subjectId,
  label = "Explain with AI",
  className = "",
}: {
  subjectType: ExplainSubject;
  subjectId: string;
  label?: string;
  className?: string;
}) {
  const [result, setResult] = useState<ExplanationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);

  async function run(detailed: boolean) {
    setLoading(true);
    try {
      const next = await explain({ subjectType, subjectId, detailed });
      setResult(next);
      if (detailed) setExpanded(true);
    } catch (error) {
      // Including a 401. Someone signed out looking at a public listing gets
      // told to sign in, not an exception.
      setResult({
        available: false,
        reason:
          error instanceof ApiError && error.status === 401
            ? "Sign in to use AI explanations."
            : "AI explanation unavailable right now. The security result below is unaffected.",
      });
    } finally {
      setLoading(false);
    }
  }

  if (!result) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => void run(false)}
        disabled={loading}
        className={className}
      >
        {loading ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
        ) : (
          <Sparkles className="size-3.5" aria-hidden="true" />
        )}
        {loading ? "Thinking…" : label}
      </Button>
    );
  }

  if (!result.available) {
    return (
      <p className={`text-xs text-muted-foreground ${className}`}>{result.reason}</p>
    );
  }

  return (
    <div
      className={`rounded-lg border border-dashed border-border bg-muted/40 p-4 ${className}`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Sparkles className="size-3.5" aria-hidden="true" />
          AI explanation
        </span>
        {/* Attribution is not optional. Fallback can change the vendor between
            one request and the next, and that has billing and privacy
            consequences the reader is entitled to see. */}
        <span className="text-[11px] text-muted-foreground">
          {result.provider} · {result.modelId}
          {result.cached ? " · cached" : ""}
        </span>
      </div>

      <p className="mt-2.5 text-sm leading-relaxed whitespace-pre-line">{result.summary}</p>

      {expanded && result.detail ? (
        <p className="mt-3 text-sm leading-relaxed whitespace-pre-line text-muted-foreground">
          {result.detail}
        </p>
      ) : null}

      <div className="mt-3 flex items-center gap-2">
        {!expanded ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => void run(true)}
            disabled={loading}
          >
            {loading ? "Thinking…" : "Explain more"}
          </Button>
        ) : null}
      </div>

      <p className="mt-3 border-t border-border pt-2.5 text-[11px] text-muted-foreground">
        Generated from Aevrin&apos;s scan evidence. It explains findings; it does not
        produce them, and it cannot change a score or a grade.
      </p>
    </div>
  );
}
