"use client";

import { useState } from "react";
import Link from "next/link";
import { Loader2, RotateCw, Sparkles } from "lucide-react";

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
 *
 * **Every failure says what happened.** The API's own reason is shown when
 * it gave one (no provider, a key the vendor rejected, a plan limit), with a
 * link to the provider settings when that is where the fix is, and a retry.
 * One generic sentence for every failure hid a route that refused every
 * request for weeks.
 */

const SETTINGS_HREF = "/settings/ai-providers";

/** Why a request failed, in words the reader can act on. */
function failureReason(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Sign in to use AI explanations.";
    if (error.status === 402) return error.message || "This plan's AI explanations for the month are used up.";
    if (error.status === 404) return "There is nothing to explain here any more: the result may have been deleted.";
    if (error.status === 429) return error.message || "Too many explanation requests. Try again in a minute.";
    if (error.status >= 400 && error.status < 500) {
      return "The explanation request was not accepted. Reload the page and try again.";
    }
  }
  return "AI explanation unavailable right now. The security result below is unaffected.";
}

/** Whether the fix for this reason is in the AI provider settings. */
function pointsAtSettings(reason: string): boolean {
  return /Settings, AI Providers|AI provider is configured|API key/i.test(reason);
}

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
  // "Explain more" failing must not throw away the explanation already shown.
  const [moreError, setMoreError] = useState<string | null>(null);

  async function run(detailed: boolean) {
    setLoading(true);
    setMoreError(null);
    try {
      const next = await explain({ subjectType, subjectId, detailed });
      if (detailed && !next.available && result?.available) {
        setMoreError(next.reason);
        return;
      }
      setResult(next);
      if (detailed) setExpanded(true);
    } catch (error) {
      const reason = failureReason(error);
      if (detailed && result?.available) setMoreError(reason);
      else setResult({ available: false, reason });
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
      <div role="status" className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground ${className}`}>
        <span>{result.reason}</span>
        {pointsAtSettings(result.reason) ? (
          <Link href={SETTINGS_HREF} className="font-medium text-foreground underline underline-offset-2">
            Open AI provider settings
          </Link>
        ) : null}
        <Button type="button" variant="ghost" size="sm" onClick={() => void run(false)} disabled={loading}>
          {loading ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <RotateCw className="size-3.5" aria-hidden="true" />
          )}
          Try again
        </Button>
      </div>
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
        {moreError ? (
          <span role="status" className="text-xs text-muted-foreground">
            {moreError}
            {pointsAtSettings(moreError) ? (
              <>
                {" "}
                <Link href={SETTINGS_HREF} className="font-medium text-foreground underline underline-offset-2">
                  Open AI provider settings
                </Link>
              </>
            ) : null}
          </span>
        ) : null}
      </div>

      <p className="mt-3 border-t border-border pt-2.5 text-[11px] text-muted-foreground">
        Generated from Aevrin&apos;s scan evidence. It explains findings; it does not
        produce them, and it cannot change a score or a grade.
      </p>
    </div>
  );
}
