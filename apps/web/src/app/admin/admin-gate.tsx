"use client";

import { useCallback, useEffect, useState } from "react";
import { KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * The login sequence for the admin panel, and the only way into it.
 *
 * Three states, each a hard gate rather than a hint:
 *   not allowlisted  -> a plain not-found. No mention that an admin panel
 *                       exists, matching the API's own 404-not-403 choice.
 *   no TOTP enrolled -> enrolment, with no skip path.
 *   session stale    -> re-verify.
 *
 * This is defence in depth, not the enforcement itself: every admin endpoint
 * independently re-derives all three checks server-side, so bypassing this
 * component in the browser buys nothing.
 */
export function AdminGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<
    | { status: "loading" }
    | { status: "denied" }
    | { status: "enrol" }
    | { status: "verify"; email: string | null }
    | { status: "ready"; email: string | null }
  >({ status: "loading" });

  const refresh = useCallback(async () => {
    try {
      const session = await api.adminSession();
      if (!session.is_admin) return setState({ status: "denied" });
      if (!session.totp_enrolled) return setState({ status: "enrol" });
      if (!session.session_fresh) return setState({ status: "verify", email: session.email });
      return setState({ status: "ready", email: session.email });
    } catch {
      setState({ status: "denied" });
    }
  }, []);

  useEffect(() => {
    // Queued rather than called inline: setState directly in an effect body
    // cascades an extra render pass, and this runs on every mount.
    const id = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(id);
  }, [refresh]);

  // An admin session goes stale on a timer, so the gate re-checks rather than
  // letting someone sit on a panel that the API has already stopped trusting.
  useEffect(() => {
    if (state.status !== "ready") return;
    const id = window.setInterval(() => void refresh(), 60_000);
    return () => window.clearInterval(id);
  }, [state.status, refresh]);

  if (state.status === "loading") {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (state.status === "denied") {
    return (
      <div className="flex min-h-svh flex-col items-center justify-center gap-2 px-6 text-center">
        <h1 className="text-2xl font-semibold">404</h1>
        <p className="text-sm text-muted-foreground">This page could not be found.</p>
      </div>
    );
  }

  if (state.status === "enrol") return <Enrol onDone={refresh} />;
  if (state.status === "verify") return <Verify email={state.email} onDone={refresh} />;

  return <>{children}</>;
}

function Enrol({ onDone }: { onDone: () => Promise<void> }) {
  const [secret, setSecret] = useState<string | null>(null);
  const [uri, setUri] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .adminTotpEnrol()
      .then((r) => {
        setSecret(r.secret);
        setUri(r.provisioning_uri);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not start enrolment."));
  }, []);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await api.adminTotpVerify(code.trim());
      await onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not verify that code.");
      setBusy(false);
    }
  }

  return (
    <Shell title="Set up two-factor authentication" icon={<ShieldCheck className="size-5 text-brand-text" />}>
      <p className="text-sm leading-relaxed text-muted-foreground">
        The admin panel can block accounts, change plans, and grant add-ons. It requires a second factor with no
        skip path. Add this to your authenticator app, then enter a code to confirm.
      </p>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {secret ? (
        <>
          <div className="space-y-2">
            <Label>Setup key</Label>
            {/* Shown once, at enrolment, and never readable again — the API
                refuses to re-issue over a confirmed enrolment. */}
            <code className="block rounded-lg border border-border bg-background px-3 py-2 font-mono text-[13px] break-all">
              {secret}
            </code>
            {uri ? (
              <p className="text-xs text-muted-foreground">
                Or open{" "}
                <a href={uri} className="text-brand-text underline underline-offset-2">
                  this link
                </a>{" "}
                on the device with your authenticator.
              </p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="enrol-code">Authentication code</Label>
            <Input
              id="enrol-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="123456"
            />
          </div>

          <Button disabled={busy || code.trim().length < 6} onClick={() => void confirm()}>
            {busy ? "Confirming…" : "Confirm and continue"}
          </Button>
        </>
      ) : !error ? (
        <Loader2 className="size-4 animate-spin text-muted-foreground" />
      ) : null}
    </Shell>
  );
}

function Verify({ email, onDone }: { email: string | null; onDone: () => Promise<void> }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.adminTotpVerify(code.trim());
      await onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not verify that code.");
      setBusy(false);
    }
  }

  return (
    <Shell title="Confirm it's you" icon={<KeyRound className="size-5 text-brand-text" />}>
      <p className="text-sm text-muted-foreground">
        {email ? `Signed in as ${email}. ` : ""}Admin sessions expire after 30 minutes of inactivity.
      </p>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <div className="space-y-2">
        <Label htmlFor="verify-code">Authentication code</Label>
        <Input
          id="verify-code"
          inputMode="numeric"
          autoComplete="one-time-code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && code.trim().length >= 6) void submit();
          }}
          placeholder="123456"
        />
      </div>
      <Button disabled={busy || code.trim().length < 6} onClick={() => void submit()}>
        {busy ? "Checking…" : "Continue"}
      </Button>
    </Shell>
  );
}

function Shell({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex min-h-svh items-center justify-center px-6">
      <div className="w-full max-w-md space-y-5 rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2.5">
          {icon}
          <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
        </div>
        {children}
      </div>
    </div>
  );
}
