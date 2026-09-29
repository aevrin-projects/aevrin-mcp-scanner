"use client";

import { useState } from "react";
import { AlertTriangle } from "lucide-react";

import {
  INSTALL_TARGET_LABELS,
  type InstallTarget,
  type ListingDetail,
} from "@/entities/marketplace";
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
 * and it never runs a server's install command. The config shown is the one
 * the detail response already carries (`install_configs`, one per supported
 * agent, secrets left blank), with every warning the builder attached, so the
 * person clicking "copy" has already seen what they are agreeing to.
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
  const agents = Object.keys(listing.installConfigs) as InstallTarget[];
  const [agent, setAgent] = useState<InstallTarget | undefined>(agents[0]);
  const selected = agent ? listing.installConfigs[agent] : undefined;
  const text = selected ? JSON.stringify(selected.config, null, 2) : "";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* A config block can be as long as the server declares. Centred by
          transform, so anything past the viewport is unreachable rather than
          merely below the fold - hence its own height cap and scroller. */}
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Install {listing.title}</DialogTitle>
          <DialogDescription>
            Aevrin prepares the configuration. You apply it, so nothing runs on
            your machine that you have not seen.
          </DialogDescription>
        </DialogHeader>

        {agents.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            This server declares no installable package or endpoint, so there is no
            configuration to offer.
          </p>
        ) : (
          <div className="space-y-4">
            <label className="block space-y-1.5 text-sm">
              <span className="font-medium">Agent</span>
              <Select
                value={agent}
                onChange={(event) => setAgent(event.target.value as InstallTarget)}
              >
                {agents.map((target) => (
                  <option key={target} value={target}>
                    {INSTALL_TARGET_LABELS[target] ?? target}
                  </option>
                ))}
              </Select>
            </label>

            {selected?.warnings.length ? (
              <ul className="space-y-2">
                {selected.warnings.map((warning) => (
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
                <CopyButton value={text} ariaLabel="configuration" />
              </div>
              <pre className="mt-2 max-h-64 overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs">
                <code>{text}</code>
              </pre>
              <p className="mt-2 text-xs text-muted-foreground">
                Secret values are left blank on purpose. Set them in your own
                environment; never commit them.
              </p>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
