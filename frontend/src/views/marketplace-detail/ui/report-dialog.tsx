"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { reportListing, type ListingDetail } from "@/entities/marketplace";
import { ApiError } from "@/shared/api";
import { Button } from "@/shared/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";
import { Input } from "@/shared/ui/input";
import { Textarea } from "@/shared/ui/textarea";
import { Select } from "@/shared/ui";

/**
 * Reporting a listing, or a security problem with the server behind it.
 *
 * The two kinds are separated because they go to different places in an
 * admin's queue and carry different urgency. A wrong description is a
 * curation task; a vulnerability in a published server is a reason to suspend
 * a listing before anyone else installs it.
 */

export function ReportDialog({
  listing,
  open,
  onOpenChange,
}: {
  listing: ListingDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [kind, setKind] = useState<"listing" | "security">("listing");
  const [reason, setReason] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      await reportListing(listing.id, kind, reason.trim(), description.trim() || undefined);
      setDone(true);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The report could not be sent. Try again shortly.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) {
          setDone(false);
          setReason("");
          setDescription("");
          setError(null);
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Report {listing.title}</DialogTitle>
          <DialogDescription>
            {done
              ? "Thank you. An administrator will review this."
              : "Tell us what is wrong with this listing, or with the server it describes."}
          </DialogDescription>
        </DialogHeader>

        {done ? null : (
          <div className="space-y-4">
            <label className="space-y-1.5 text-sm">
              <span className="font-medium">What kind of problem?</span>
              <Select
                value={kind}
                onChange={(event) => setKind(event.target.value as "listing" | "security")}
              >
                <option value="listing">
                  The listing is wrong (metadata, category, description)
                </option>
                <option value="security">
                  A security problem with this server
                </option>
              </Select>
            </label>

            <label className="space-y-1.5 text-sm">
              <span className="font-medium">Summary</span>
              <Input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder={
                  kind === "security"
                    ? "e.g. the published package differs from the repository"
                    : "e.g. this is categorised as a database, but it is a search tool"
                }
                maxLength={300}
              />
            </label>

            <label className="space-y-1.5 text-sm">
              <span className="font-medium">Details (optional)</span>
              <Textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={4}
                maxLength={4000}
                placeholder="Anything that would help someone verify this."
              />
            </label>

            {error ? <p className="text-sm text-severity-critical">{error}</p> : null}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {done ? "Close" : "Cancel"}
          </Button>
          {done ? null : (
            <Button onClick={() => void submit()} disabled={submitting || reason.trim().length < 3}>
              {submitting ? (
                <>
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  Sending
                </>
              ) : (
                "Send report"
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
