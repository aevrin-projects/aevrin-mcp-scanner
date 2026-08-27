"use client";

import { Suspense, useActionState, useState, type ChangeEvent } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import {
  signInWithGoogle,
  signInWithGithub,
  signInWithPassword,
  signUpWithPassword,
  verifySignupCode,
  resendSignupCode,
  requestPasswordReset,
  resendPasswordResetCode,
  verifyPasswordResetCode,
  type LoginState,
  type ResetState,
} from "../api/actions";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { Separator } from "@/shared/ui/separator";
import { BrandIcon } from "@/shared/ui/brand-icon";
import { DashboardPreview } from "@/widgets/dashboard-preview";

const idleState: LoginState = { status: "idle" };
const idleResetState: ResetState = { status: "idle" };

// Supabase's configured email-OTP length for this project, confirmed by
// inspecting a real delivered code, not assumed. The code input previously
// capped at 6 characters, silently truncating every code before submit, so
// no code could ever verify (see auth/actions.ts's verifySignupCode).
const OTP_LENGTH = 8;

function stripNonDigits(e: ChangeEvent<HTMLInputElement>) {
  e.currentTarget.value = e.currentTarget.value.replace(/\D/g, "").slice(0, OTP_LENGTH);
}

/* Brand marks come from `thesvg` rather than path data copied into this file:
   the previous Google glyph was a single-path monochrome approximation, not
   the actual four-colour mark. GitHub's near-black brand colour is recoloured
   to the current text colour by BrandIcon, so it survives both themes. */
function GoogleIcon() {
  return <BrandIcon name="google" className="size-4" />;
}

function GitHubIcon() {
  return <BrandIcon name="github" className="size-4" />;
}

// Site chrome (navbar) stays mounted around this page, the sign-in flow
// previously hid the navbar entirely and forced a full-viewport card, which
// made the site feel like a dead end with no way back. This shell instead
// fills the space under the sticky navbar (h-14) and keeps the rest of the
// site one click away at all times.
//
// The split panel itself is deliberately NOT stretched to fill that whole
// height, on a large/tall viewport, a `min-h-svh` grid pulls the marketing
// copy and the card apart into huge empty voids on each side. Capping the
// panel nearly fills the available viewport while keeping a deliberate
// breathing gap around it. The form column scrolls independently for the
// longer verification and reset states.
function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="auth-ambient relative grid min-h-svh w-full overflow-hidden bg-background lg:grid-cols-[0.92fr_1.08fr]">
      <div className="security-mesh absolute inset-0 opacity-35" aria-hidden="true" />
      <div className="security-orb security-orb-one" aria-hidden="true" />
      <div className="security-orb security-orb-two" aria-hidden="true" />
      <h1 className="sr-only">Aevrin account access</h1>

      {/* Full-bleed split. No card, no page padding, no max width, the two
          columns run edge to edge and the whole thing is exactly one viewport
          tall at every size. Form first in DOM and visual order: it's the
          only thing anyone came here to do, so it gets the first tab stop. */}
      <div className="relative z-10 flex min-h-svh flex-col overflow-y-auto px-5 py-6 sm:px-8 lg:px-12">
        <Link href="/" className="inline-flex w-fit items-center gap-2.5 text-sm font-semibold tracking-[0.14em] uppercase">
          <Image src="/logo.png" alt="" width={22} height={24} priority />
          Aevrin
        </Link>

        <div className="flex flex-1 items-center justify-center py-8">
          <div className="w-full max-w-md">{children}</div>
        </div>

      </div>

      {/* Product panel. `overflow-hidden` is what lets the device frame inside
          bleed off the right edge instead of forcing a horizontal scrollbar. */}
      <div className="auth-grid relative hidden min-h-svh flex-col justify-center gap-10 overflow-hidden border-l border-border bg-muted/40 py-12 pl-12 lg:flex xl:pl-16">
        <div className="auth-scan-line" aria-hidden="true" />
        <div className="flex max-w-lg flex-col gap-3 pr-12">
          <h2 className="text-2xl font-semibold tracking-tight text-balance xl:text-3xl">
            Every finding comes with evidence and a fix.
          </h2>
          <p className="text-sm leading-relaxed text-muted-foreground">
            A score you can act on, the exact file and line that raised it, the scanner behind it,
            and a remediation written against that code.
          </p>
        </div>

        {/* Wider than its column and clipped by the panel, so the dashboard
            runs off the right edge rather than ending in an awkward margin. */}
        <div className="w-[min(118%,940px)]">
          <DashboardPreview className="rounded-r-none border-r-0" />
        </div>
      </div>
    </div>
  );
}

export function LoginPage() {
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
          <div className="flex flex-col gap-2 sm:flex-row">
            <form action={signInWithGoogle} className="flex-1">
              <input type="hidden" name="next" value={next} />
              <Button type="submit" variant="outline" className="w-full gap-2">
                <GoogleIcon />
                Google
              </Button>
            </form>
            <form action={signInWithGithub} className="flex-1">
              <input type="hidden" name="next" value={next} />
              <Button type="submit" variant="outline" className="w-full gap-2">
                <GitHubIcon />
                GitHub
              </Button>
            </form>
          </div>
          {mode === "signup" && (
            <p className="text-center text-xs text-muted-foreground">
              By continuing with Google or GitHub, you agree to the{" "}
              <Link href="/terms" target="_blank" className="underline underline-offset-2 hover:text-foreground">
                Terms of Service
              </Link>{" "}
              and{" "}
              <Link href="/privacy" target="_blank" className="underline underline-offset-2 hover:text-foreground">
                Privacy Policy
              </Link>
              .
            </p>
          )}

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
            {mode === "signup" && (
              <div className="flex items-start gap-2">
                <input
                  id="accept-terms"
                  name="acceptTerms"
                  type="checkbox"
                  required
                  className="mt-0.5 size-4 shrink-0 rounded border-input"
                />
                <Label htmlFor="accept-terms" className="text-xs font-normal leading-relaxed text-muted-foreground">
                  I agree to the{" "}
                  <Link href="/terms" target="_blank" className="underline underline-offset-2 hover:text-foreground">
                    Terms of Service
                  </Link>{" "}
                  and{" "}
                  <Link href="/privacy" target="_blank" className="underline underline-offset-2 hover:text-foreground">
                    Privacy Policy
                  </Link>
                  .
                </Label>
              </div>
            )}
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
