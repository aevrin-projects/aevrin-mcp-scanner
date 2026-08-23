"use client";

import { useEffect, useState } from "react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { deviceApi } from "@/entities/device";
import { ApiError } from "@/shared/api";

type Status = "entering" | "approving" | "approved" | "error";

export function DeviceApproveForm({ initialUserCode }: { initialUserCode: string }) {
  const [userCode, setUserCode] = useState(initialUserCode);
  const [clientKind, setClientKind] = useState<string | null>(null);
  const [fingerprint, setFingerprint] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("entering");
  const [message, setMessage] = useState<string | null>(null);

  // Open-source FingerprintJS core (no account/API key), abuse-prevention
  // signal only, per addendum §4's own "don't over-build this" guidance.
  // Loaded dynamically since it touches browser-only APIs.
  useEffect(() => {
    let cancelled = false;
    import("@fingerprintjs/fingerprintjs")
      .then((FingerprintJS) => FingerprintJS.load())
      .then((fp) => fp.get())
      .then((result) => {
        if (!cancelled) setFingerprint(result.visitorId);
      })
      .catch(() => {
        // Best-effort: approval still works without a fingerprint, it just
        // contributes one fewer abuse-prevention signal.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const normalized = userCode.trim().toUpperCase();
    if (normalized.length !== 9) {
      return;
    }
    let cancelled = false;
    deviceApi.getDeviceCodeInfo(normalized)
      .then((info) => {
        if (!cancelled) setClientKind(info.client_kind);
      })
      .catch(() => {
        if (!cancelled) setClientKind(null);
      });
    return () => {
      cancelled = true;
    };
  }, [userCode]);

  async function handleApprove(e: React.FormEvent) {
    e.preventDefault();
    const normalized = userCode.trim().toUpperCase();
    setStatus("approving");
    setMessage(null);
    try {
      await deviceApi.approveDevice(normalized, fingerprint);
      setStatus("approved");
    } catch (err) {
      setStatus("error");
      setMessage(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    }
  }

  if (status === "approved") {
    return (
      <div className="flex min-h-[calc(100svh-3.5rem)] items-center justify-center bg-background px-4">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle className="text-xl">Device connected</CardTitle>
            <CardDescription>You can close this tab and return to your terminal.</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  // Derived from length rather than trusting stale state: if the user edits
  // the code back below 9 chars, the label should disappear immediately
  // rather than showing an answer for a code that's no longer fully entered.
  const codeComplete = userCode.trim().length === 9;
  const clientKindLabel =
    codeComplete && clientKind === "cli"
      ? "the Aevrin CLI"
      : codeComplete && clientKind === "hook"
        ? "the Claude Code hook"
        : null;

  return (
    <div className="flex min-h-[calc(100svh-3.5rem)] items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">Connect a device</CardTitle>
          <CardDescription>
            {clientKindLabel
              ? `Confirm this code to sign in ${clientKindLabel} on your machine.`
              : "Enter the code shown in your terminal."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleApprove} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="user_code">Code</Label>
              <Input
                id="user_code"
                value={userCode}
                onChange={(e) => setUserCode(e.target.value.toUpperCase())}
                placeholder="WXYZ-1234"
                maxLength={9}
                className="text-center font-mono text-lg tracking-widest"
                required
                autoFocus
              />
            </div>
            {status === "error" && (
              <p className="text-sm text-destructive" role="alert">
                {message}
              </p>
            )}
            <Button type="submit" disabled={status === "approving" || userCode.trim().length !== 9} className="w-full">
              {status === "approving" ? "Connecting…" : "Approve"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
