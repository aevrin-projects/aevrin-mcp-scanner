import Link from "next/link";
import { ShieldCheck } from "lucide-react";

import { buttonVariants } from "@/shared/ui/button";
import { CopyButton } from "@/shared/ui/copy-button";
import { scanHandoff } from "../model/scan-handoff";
import type { ListingDetail } from "../model/types";

/**
 * "Scan with Aevrin", for MCP servers only. Hands off to the scan page (or
 * the CLI command) and says nothing about the server's security itself: the
 * registry holds no scan result, and the scan that runs is the user's own.
 * Renders nothing when there is no unambiguous target to hand off.
 */
export function ScanWithAevrin({
  listing,
}: {
  listing: Pick<ListingDetail, "itemType" | "repositoryUrl" | "installation">;
}) {
  const handoff = scanHandoff(listing);
  if (!handoff) return null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border p-4">
      <p className="min-w-0 flex-1 text-sm text-muted-foreground">
        The registry does not scan what it lists. To check this server, scan it with
        Aevrin: the result is your own scan, on your scans page.
      </p>
      {handoff.kind === "link" ? (
        <Link href={handoff.href} className={buttonVariants({ variant: "outline", size: "sm" })}>
          <ShieldCheck className="size-4" aria-hidden="true" />
          Scan with Aevrin
        </Link>
      ) : (
        <div className="w-full space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">
              Published only as a package, so it is scanned from the Aevrin CLI:
            </p>
            <CopyButton value={handoff.command} ariaLabel="scan command" />
          </div>
          <pre className="overflow-x-auto rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-xs whitespace-pre-wrap break-all">
            {handoff.command}
          </pre>
        </div>
      )}
    </div>
  );
}
