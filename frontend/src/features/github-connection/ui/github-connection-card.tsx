"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { GitPullRequest } from "lucide-react";
import { toast } from "sonner";
import { ApiError } from "@/shared/api";
import { githubApi } from "@/entities/github";
import { SectionCard } from "@/shared/ui";
import { Button } from "@/shared/ui/button";

// Each of these is a genuinely different outcome. They were previously all
// reported as "cancelled", which told someone who had just granted access
// that they hadn't -- the exact confusion behind "I approved it and nothing
// updated".
const CALLBACK_MESSAGE: Record<string, { message: string; ok: boolean }> = {
  connected: {
    message: "GitHub connected: Aevrin can now scan the repositories you granted.",
    ok: true,
  },
  cancelled: { message: "GitHub connection cancelled; nothing was granted.", ok: false },
  invalid_state: { message: "That connection link expired, try connecting again.", ok: false },
  authorized_not_installed: {
    message:
      "You authorized Aevrin but didn't finish installing it, so it has no repository access yet. Use Connect GitHub and pick the repositories on the install screen.",
    ok: false,
  },
  needs_relink: {
    message:
      "Installed on GitHub, but it arrived without the link that ties it to this Aevrin account. Click Connect GitHub here to finish; it won't ask for access again.",
    ok: false,
  },
  updated: {
    message: "GitHub access updated: your repository list here now matches what you granted.",
    ok: true,
  },
  approval_pending: {
    message:
      "Requested: an owner of that GitHub organization has to approve the install before it takes effect.",
    ok: false,
  },
  error: { message: "Could not complete the GitHub connection, try again.", ok: false },
};

/**
 * Connecting GitHub is an integration, so it lives with the other
 * integrations. It used to sit on the billing page as an "add-on" priced
 * "Included", which put a thing you cannot buy in a row of things you can.
 */
export function GithubConnectionCard() {
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<{ connected: boolean; account_login: string | null } | null>(
    null,
  );
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    githubApi
      .getStatus()
      .then(setStatus)
      .catch((err) =>
        toast.error(
          err instanceof ApiError ? err.message : "Could not load GitHub connection status.",
        ),
      );
  }, []);

  useEffect(() => {
    const result = searchParams.get("github");
    if (!result) return;
    const outcome = CALLBACK_MESSAGE[result];
    if (!outcome) return;
    if (outcome.ok) toast.success(outcome.message);
    else toast.error(outcome.message);
  }, [searchParams]);

  async function connect() {
    setConnecting(true);
    try {
      const { url } = await githubApi.getInstallUrl();
      window.location.href = url;
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not start GitHub connection.");
      setConnecting(false);
    }
  }

  return (
    <SectionCard
      title="GitHub"
      description="Required before Aevrin can scan a private repository on your behalf."
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <GitPullRequest className="size-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <p className="text-sm">
              {status === null
                ? "Checking connection status…"
                : status.connected
                  ? `Connected as ${status.account_login}. Aevrin can scan the repositories you granted.`
                  : "Not connected. Private repositories cannot be scanned until you connect."}
            </p>
            <ul className="mt-2 flex flex-col gap-1 text-[13px] leading-5 text-muted-foreground">
              <li>Scoped to the repositories you pick</li>
              <li>Read-only: Aevrin reads code to scan it and writes nothing back</li>
              <li>Revocable from GitHub at any time</li>
            </ul>
          </div>
        </div>
        <div>
          {status?.connected ? (
            <Button variant="outline" disabled>
              Connected
            </Button>
          ) : (
            <Button variant="outline" disabled={connecting} onClick={() => void connect()}>
              {connecting ? "Redirecting…" : "Connect GitHub"}
            </Button>
          )}
        </div>
      </div>
    </SectionCard>
  );
}
