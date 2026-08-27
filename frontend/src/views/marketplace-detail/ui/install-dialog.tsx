"use client";

import { useState } from "react";
import { AlertTriangle, Loader2, ShieldAlert } from "lucide-react";

import {
  GradeBadge,
  INSTALL_TARGET_LABELS,
  getInstallPlan,
  type InstallPlan,
  type InstallTarget,
  type ListingDetail,
} from "@/entities/marketplace";
import { ApiError } from "@/shared/api";
import { Button } from "@/shared/ui/button";
import { CopyButton } from "@/shared/ui/copy-button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";
import { Select } from "@/shared/ui";

/**
 * The install step, which deliberately does not install anything.
 *
 * Aevrin does not reach into a developer's machine and write configuration,
 * and it never runs a server's install command to find out what it does.
 * What this produces is the exact config to apply, shown alongside the grade,
 * the declared capabilities, and every warning the plan carries — so the
 * person clicking "copy" has already seen what they are agreeing to.
 *
 * A workspace policy that blocks this grade stops the flow here with the
 * reason, rather than letting someone copy a config their organisation has
 * decided against.
 */

export function InstallDialog({
  listing,
  open,
  onOpenChange,
}: {
  listing: ListingDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const targets = listing.installTargets as InstallTarget[];
  const [agent, setAgent] = useState<InstallTarget>(targets[0] ?? "generic");
  const [scope, setScope] = useState<"global" | "project">("global");
  const [plan, setPlan] = useState<InstallPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function buildPlan() {
    setLoading(true);
    setError(null);
    setPlan(null);
    try {
      setPlan(await getInstallPlan(listing.slug, agent, scope));
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The install plan could not be prepared.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Install {listing.title}</DialogTitle>
          <DialogDescription>
            Aevrin prepares the configuration. You apply it, so nothing runs on
            your machine that you have not seen.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="rounded-lg border border-border p-4">
            <GradeBadge
              grade={listing.security.grade}
              score={listing.security.score}
              state={listing.security.state}
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1.5 text-sm">
              <span className="font-medium">Agent</span>
              <Select
                value={agent}
                onChange={(event) => setAgent(event.target.value as InstallTarget)}
              >
                {targets.map((target) => (
                  <option key={target} value={target}>
                    {INSTALL_TARGET_LABELS[target] ?? target}
                  </option>
                ))}
              </Select>
            </label>

            <label className="space-y-1.5 text-sm">
              <span className="font-medium">Scope</span>
              <Select
                value={scope}
                onChange={(event) => setScope(event.target.value as "global" | "project")}
              >
                <option value="global">Global</option>
                <option value="project">This project</option>
              </Select>
            </label>
          </div>

          {error ? (
            <div className="flex items-start gap-3 rounded-lg border border-severity-critical/25 bg-severity-critical/10 p-3 text-sm">
              <ShieldAlert
                className="mt-0.5 size-4 shrink-0 text-severity-critical"
                aria-hidden="true"
              />
              <p>{error}</p>
            </div>
          ) : null}

          {plan ? (
            <>
              {plan.policyAction === "require_approval" ? (
                <div className="flex items-start gap-3 rounded-lg border border-severity-medium/25 bg-severity-medium/10 p-3 text-sm">
                  <AlertTriangle
                    className="mt-0.5 size-4 shrink-0 text-severity-medium"
                    aria-hidden="true"
                  />
                  <p>
                    Your workspace policy requires approval for this server.{" "}
                    {plan.policyReason}
                  </p>
                </div>
              ) : null}

              {plan.capabilities.length > 0 ? (
                <div>
                  <p className="text-sm font-medium">Declared capabilities</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    From this server&apos;s own metadata. What it asks for, not what
                    it has been observed doing.
                  </p>
                  <ul className="mt-2 space-y-1 text-sm">
                    {plan.capabilities.map((capability) => (
                      <li key={capability} className="text-muted-foreground">
                        · {capability}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {plan.warnings.length > 0 ? (
                <ul className="space-y-2">
                  {plan.warnings.map((warning) => (
                    <li
                      key={warning}
                      className="flex items-start gap-2.5 rounded-md border border-border bg-muted/40 p-3 text-sm"
                    >
                      <AlertTriangle
                        className="mt-0.5 size-3.5 shrink-0 text-severity-medium"
                        aria-hidden="true"
                      />
                      <span>{warning}</span>
                    </li>
                  ))}
                </ul>
              ) : null}

              <div>
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium">Configuration</p>
                  <CopyButton value={JSON.stringify(plan.config, null, 2)} />
                </div>
                <pre className="mt-2 max-h-64 overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs">
                  <code>{JSON.stringify(plan.config, null, 2)}</code>
                </pre>
                <p className="mt-2 text-xs text-muted-foreground">
                  Secret values are left blank on purpose. Set them in your own
                  environment; never commit them.
                </p>
              </div>
            </>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => void buildPlan()} disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                Preparing
              </>
            ) : plan ? (
              "Rebuild plan"
            ) : (
              "Prepare install"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
