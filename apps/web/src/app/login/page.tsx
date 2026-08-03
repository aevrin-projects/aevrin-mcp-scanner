"use client";

import { Suspense, useActionState, useState, type ChangeEvent } from "react";
import { useSearchParams } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { FileWarning, ShieldCheck, Terminal } from "lucide-react";
import {
  signInWithGoogle,
  signInWithPassword,
  signUpWithPassword,
  verifySignupCode,
  resendSignupCode,
  requestPasswordReset,
  resendPasswordResetCode,
  verifyPasswordResetCode,
  type LoginState,
  type ResetState,
} from "./actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

const idleState: LoginState = { status: "idle" };
const idleResetState: ResetState = { status: "idle" };

// Supabase's configured email-OTP length for this project — confirmed by
// inspecting a real delivered code, not assumed. The code input previously
// capped at 6 characters, silently truncating every code before submit, so
// no code could ever verify (see auth/actions.ts's verifySignupCode).
const OTP_LENGTH = 8;

function stripNonDigits(e: ChangeEvent<HTMLInputElement>) {
  e.currentTarget.value = e.currentTarget.value.replace(/\D/g, "").slice(0, OTP_LENGTH);
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true">
      <path
        fill="currentColor"
        d="M21.35 11.1h-9.17v2.73h6.51c-.33 3.81-3.5 5.44-6.5 5.44C8.36 19.27 5 16.25 5 12c0-4.1 3.2-7.27 7.2-7.27 3.09 0 4.9 1.97 4.9 1.97L19 4.72S16.56 2 12.1 2C6.42 2 2.03 6.8 2.03 12c0 5.05 4.13 10 10.22 10 5.35 0 9.25-3.67 9.25-9.09 0-1.15-.17-1.81-.17-1.81Z"
      />
    </svg>
  );
}

// Site chrome (navbar) stays mounted around this page — the sign-in flow
// previously hid the navbar entirely and forced a full-viewport card, which
// made the site feel like a dead end with no way back. This shell instead
// fills the space under the sticky navbar (h-14) and keeps the rest of the
// site one click away at all times.
//
// The split panel itself is deliberately NOT stretched to fill that whole
// height — on a large/tall viewport, a `min-h-svh` grid pulls the marketing
// copy and the card apart into huge empty voids on each side. Capping the
// panel to `max-w-5xl`/`lg:h-[600px]` and centering it in the available
// space keeps its proportions consistent across viewport sizes instead of
// stretching edge-to-edge.
function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="auth-ambient relative flex min-h-[calc(100svh-3.5rem)] items-center justify-center overflow-hidden bg-background p-4 lg:p-10">
      <div className="security-mesh absolute inset-0 opacity-35" aria-hidden="true" />
      <div className="security-orb security-orb-one" aria-hidden="true" />
      <div className="security-orb security-orb-two" aria-hidden="true" />
      <h1 className="sr-only">Aevrin account access</h1>
      <div className="auth-panel-enter relative grid w-full max-w-5xl overflow-hidden rounded-[28px] border border-border/80 bg-background/88 shadow-2xl shadow-black/15 backdrop-blur-xl lg:h-[600px] lg:grid-cols-2">
        <div className="auth-grid relative hidden flex-col justify-center gap-8 overflow-hidden border-r border-border bg-muted/40 p-10 lg:flex">
          <div className="auth-scan-line" aria-hidden="true" />
          <Link href="/" className="flex items-center gap-2 font-semibold">
            <Image src="/logo.png" alt="" width={22} height={24} />
            <span>Aevrin</span>
          </Link>
          <div className="flex max-w-sm flex-col gap-6">
            <h2 className="text-2xl font-semibold tracking-tight text-balance">
              Know what your MCP servers can actually do before you install them.
            </h2>
            <ul className="flex flex-col gap-4 text-sm text-muted-foreground">
              <li className="flex items-start gap-3">
                <ShieldCheck className="mt-0.5 size-4 shrink-0 text-foreground" />
                <span>Static analysis against the OWASP MCP Top 10 — nothing runs against production traffic.</span>
              </li>
              <li className="flex items-start gap-3">
                <Terminal className="mt-0.5 size-4 shrink-0 text-foreground" />
                <span>Scan from the CLI, a Claude Code hook, or paste a repo URL straight into the dashboard.</span>
              </li>
              <li className="flex items-start gap-3">
                <FileWarning className="mt-0.5 size-4 shrink-0 text-foreground" />
                <span>Every finding is scored and mapped to a fix — not a wall of raw tool output.</span>
              </li>
            </ul>
            <div className="flex items-center gap-3 rounded-2xl border border-brand/25 bg-background/65 px-4 py-3 text-xs text-muted-foreground backdrop-blur-sm">
              <span className="relative flex size-2">
                <span className="absolute inline-flex size-full rounded-full bg-brand opacity-60 motion-safe:animate-ping" />
                <span className="relative inline-flex size-2 rounded-full bg-brand" />
              </span>
              Dashboard, CLI, and hook evidence stay in sync.
            </div>
          </div>
          <p className="text-xs text-muted-foreground">© {new Date().getFullYear()} Aevrin</p>
        </div>
        <div className="relative flex items-center justify-center overflow-y-auto bg-background/70 p-6 sm:p-8">
          <div className="w-full max-w-sm py-8">{children}</div>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const searchParams = useSearchParams();
  const next = searchParams.get("next") ?? "/dashboard";
  const [mode, setMode] = useState<"signin" | "signup" | "reset">("signin");
  const [signInState, signInAction, signInPending] = useActionState(signInWithPassword, idleState);
  const [signUpState, signUpAction, signUpPending] = useActionState(signUpWithPassword, idleState);
  const [verifyState, verifyAction, verifyPending] = useActionState(verifySignupCode, idleState);
  const [resendState, resendAction] = useActionState(resendSignupCode, idleState);

  const [resetRequestState, resetRequestAction, resetRequestPending] = useActionState(
    requestPasswordReset,
    idleResetState,
  );
  const [resetVerifyState, resetVerifyAction, resetVerifyPending] = useActionState(
    verifyPasswordResetCode,
    idleResetState,
  );
  const [resetResendState, resetResendAction] = useActionState(resendPasswordResetCode, idleResetState);

  // Unconditional on `mode` so this also catches the "sign in with Google
  // first, set a password" path below, which requests a reset code without
  // ever switching into mode "reset".
  const codeSent = resetVerifyState.status === "code-sent" ? resetVerifyState : resetRequestState;
  if (codeSent.status === "code-sent" && codeSent.email) {
    const email = codeSent.email;
    return (
      <AuthShell>
        <Card className="w-full">
          <CardHeader>
            <CardTitle className="text-xl">Set your password</CardTitle>
            <CardDescription>{resetResendState.message ?? codeSent.message}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <form action={resetVerifyAction} className="flex flex-col gap-4">
              <input type="hidden" name="email" value={email} />
              <div className="flex flex-col gap-2">
                <Label htmlFor="reset-code">Code</Label>
                <Input
                  id="reset-code"
                  name="code"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={OTP_LENGTH}
                  onChange={stripNonDigits}
                  placeholder="12345678"
                  required
                  autoFocus
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="new-password">New password</Label>
                <Input
                  id="new-password"
                  name="newPassword"
                  type="password"
                  autoComplete="new-password"
                  placeholder="At least 8 characters"
                  minLength={8}
                  required
                />
              </div>
              {resetVerifyState.status === "error" && (
                <p className="text-sm text-destructive" role="alert">
                  {resetVerifyState.message}
                </p>
              )}
              <Button type="submit" disabled={resetVerifyPending} className="w-full">
                {resetVerifyPending ? "Saving…" : "Save password"}
              </Button>
            </form>
            <form action={resetResendAction}>
              <input type="hidden" name="email" value={email} />
              <Button type="submit" variant="ghost" className="w-full text-sm">
                Resend code
              </Button>
            </form>
          </CardContent>
        </Card>
      </AuthShell>
    );
  }

  if (mode === "reset") {
    return (
      <AuthShell>
        <Card className="w-full">
          <CardHeader>
            <CardTitle className="text-xl">Reset your password</CardTitle>
            <CardDescription>We&apos;ll email you a code.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <form action={resetRequestAction} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="reset-email">Email</Label>
                <Input
                  id="reset-email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@company.com"
                  required
                  autoFocus
                />
              </div>
              {resetRequestState.status === "error" && (
                <p className="text-sm text-destructive" role="alert">
                  {resetRequestState.message}
                </p>
              )}
              <Button type="submit" disabled={resetRequestPending} className="w-full">
                {resetRequestPending ? "Sending…" : "Send reset code"}
              </Button>
            </form>
            <button
              type="button"
              onClick={() => setMode("signin")}
              className="text-center text-sm text-muted-foreground hover:text-foreground"
            >
              Back to sign in
            </button>
          </CardContent>
        </Card>
      </AuthShell>
    );
  }

  const pendingVerify = verifyState.status === "verify-code" ? verifyState : signUpState;
  const showVerifyStep = pendingVerify.status === "verify-code" && pendingVerify.email;

  if (showVerifyStep) {
    const email = pendingVerify.email!;
    return (
      <AuthShell>
        <Card className="w-full">
          <CardHeader>
            <CardTitle className="text-xl">Check your email</CardTitle>
            <CardDescription>{resendState.message ?? pendingVerify.message}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <form action={verifyAction} className="flex flex-col gap-4">
              <input type="hidden" name="email" value={email} />
              <input type="hidden" name="next" value={next} />
              <div className="flex flex-col gap-2">
                <Label htmlFor="code">Code</Label>
                <Input
                  id="code"
                  name="code"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={OTP_LENGTH}
                  onChange={stripNonDigits}
                  placeholder="12345678"
                  required
                  autoFocus
                />
              </div>
              {verifyState.status === "error" && (
                <p className="text-sm text-destructive" role="alert">
                  {verifyState.message}
                </p>
              )}
              <Button type="submit" disabled={verifyPending} className="w-full">
                {verifyPending ? "Verifying…" : "Verify and continue"}
              </Button>
            </form>
            <form action={resendAction}>
              <input type="hidden" name="email" value={email} />
              <Button type="submit" variant="ghost" className="w-full text-sm">
                Resend code
              </Button>
            </form>
          </CardContent>
        </Card>
      </AuthShell>
    );
  }

  if (signInState.status === "google-only" && signInState.email) {
    const email = signInState.email;
    return (
      <AuthShell>
        <Card className="w-full">
          <CardHeader>
            <CardTitle className="text-xl">This email uses Google sign-in</CardTitle>
            <CardDescription>{signInState.message}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <form action={signInWithGoogle}>
              <input type="hidden" name="next" value={next} />
              <Button type="submit" variant="outline" className="w-full gap-2">
                <GoogleIcon />
                Continue with Google
              </Button>
            </form>
            <div className="flex items-center gap-3">
              <Separator className="flex-1" />
              <span className="text-xs text-muted-foreground">or</span>
              <Separator className="flex-1" />
            </div>
            <form action={resetRequestAction}>
              <input type="hidden" name="email" value={email} />
              <Button type="submit" variant="secondary" disabled={resetRequestPending} className="w-full">
                {resetRequestPending ? "Sending…" : "Email me a code to set a password"}
              </Button>
            </form>
            <button
              type="button"
              onClick={() => setMode("signin")}
              className="text-center text-sm text-muted-foreground hover:text-foreground"
            >
              Back to sign in
            </button>
          </CardContent>
        </Card>
      </AuthShell>
    );
  }

  const activeState = mode === "signin" ? signInState : signUpState;
  const activeAction = mode === "signin" ? signInAction : signUpAction;
  const activePending = mode === "signin" ? signInPending : signUpPending;

  return (
    <AuthShell>
      <Card className="w-full">
        <CardHeader>
          <CardTitle className="text-xl">{mode === "signin" ? "Sign in to Aevrin" : "Create your Aevrin account"}</CardTitle>
          <CardDescription>
            {mode === "signin" ? "Welcome back." : "We'll email you a code to verify your address."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <form action={signInWithGoogle}>
            <input type="hidden" name="next" value={next} />
            <Button type="submit" variant="outline" className="w-full gap-2">
              <GoogleIcon />
              Continue with Google
            </Button>
          </form>

          <div className="flex items-center gap-3">
            <Separator className="flex-1" />
            <span className="text-xs text-muted-foreground">or</span>
            <Separator className="flex-1" />
          </div>

          <form action={activeAction} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@company.com"
                required
                autoFocus
              />
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Password</Label>
                {mode === "signin" && (
                  <button
                    type="button"
                    onClick={() => setMode("reset")}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    Forgot password?
                  </button>
                )}
              </div>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete={mode === "signup" ? "new-password" : "current-password"}
                placeholder={mode === "signup" ? "At least 8 characters" : "••••••••"}
                required
                minLength={mode === "signup" ? 8 : undefined}
              />
            </div>
            {activeState.status === "error" && (
              <p className="text-sm text-destructive" role="alert">
                {activeState.message}
              </p>
            )}
            <Button type="submit" disabled={activePending} className="w-full">
              {activePending ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
            </Button>
          </form>

          <button
            type="button"
            onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
            className="text-center text-sm text-muted-foreground hover:text-foreground"
          >
            {mode === "signin" ? "New here? Create an account" : "Already have an account? Sign in"}
          </button>
        </CardContent>
      </Card>
    </AuthShell>
  );
}
