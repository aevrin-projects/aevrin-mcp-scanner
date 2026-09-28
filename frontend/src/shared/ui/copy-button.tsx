"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/shared/ui/button";

/**
 * `ariaLabel` names what is being copied. A page with several of these would
 * otherwise read as a row of identical "Copy" buttons to a screen reader.
 */
export function CopyButton({
  value,
  label = "Copy",
  ariaLabel,
}: {
  value: string;
  label?: string;
  ariaLabel?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={handleCopy}
      aria-label={ariaLabel ? (copied ? `Copied: ${ariaLabel}` : `Copy ${ariaLabel}`) : undefined}
    >
      {copied ? <Check className="size-4" aria-hidden="true" /> : <Copy className="size-4" aria-hidden="true" />}
      {copied ? "Copied" : label}
    </Button>
  );
}
