"use client";

import { useCallback, useEffect, useState } from "react";
import { notFound } from "next/navigation";
import { KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { ApiError } from "@/shared/api";
import { adminApi } from "@/entities/admin";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { TotpQr } from "./totp-qr";

/**
 * The login sequence for the admin panel, and the only way into it.
 *
 * Three states, each a hard gate rather than a hint:
 *   not allowlisted  -> the app's real 404 page, indistinguishable from a
 *                       route that doesn't exist. Matches the API's own
 *                       404-not-403 choice.
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
      const session = await adminApi.getSession();
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
    // The app's real not-found page, not a hand-rolled lookalike, anyone
    // who isn't allowlisted should be unable to tell this route exists at
    // all, which a bespoke 404 screen would give away.
    notFound();
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
    adminApi
      .enrolTotp()
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
      await adminApi.verifyTotp(code.trim());
      await onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not verify that code.");
      setBusy(false);
    }
  }

  return (
    <Shell title="Set up two-factor authentication" icon={<ShieldCheck className="size-5 text-brand-text" />}>
      <p className="text-sm leading-relaxed text-muted-foreground">
        The admin panel can block accounts, change plans, and delete accounts outright. It requires a second factor with no
        skip path. Add this to your authenticator app, then enter a code to confirm.
      </p>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      {secret ? (
        <>
          {uri ? (
            <div className="flex flex-col items-center gap-2">
              <div className="rounded-xl border border-border bg-white p-3">
                <TotpQr uri={uri} />
              </div>
              <p className="text-xs text-muted-foreground">Scan this with your authenticator app.</p>
            </div>
          ) : null}

          <div className="space-y-2">
            {/* The key stays, below the QR rather than instead of it: a
                desktop browser cannot scan its own screen, and some
                authenticators still only accept typed entry. */}
            <Label>Or enter this setup key manually</Label>
            {/* Shown once, at enrolment, and never readable again, the API
                refuses to re-issue over a confirmed enrolment. */}
            <code className="block rounded-lg border border-border bg-background px-3 py-2 font-mono text-[13px] break-all">
              {secret}
            </code>
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
      await adminApi.verifyTotp(code.trim());
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
