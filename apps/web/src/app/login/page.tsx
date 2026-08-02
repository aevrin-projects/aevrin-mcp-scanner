"use client";

import { Suspense, useActionState, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  signInWithGoogle,
  signInWithPassword,
  signUpWithPassword,
  verifySignupCode,
  resendSignupCode,
  type LoginState,
} from "./actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

const idleState: LoginState = { status: "idle" };

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
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [signInState, signInAction, signInPending] = useActionState(signInWithPassword, idleState);
  const [signUpState, signUpAction, signUpPending] = useActionState(signUpWithPassword, idleState);
  const [verifyState, verifyAction, verifyPending] = useActionState(verifySignupCode, idleState);
  const [resendState, resendAction] = useActionState(resendSignupCode, idleState);

  const pendingVerify = verifyState.status === "verify-code" ? verifyState : signUpState;
  const showVerifyStep = pendingVerify.status === "verify-code" && pendingVerify.email;

  if (showVerifyStep) {
    const email = pendingVerify.email!;
    return (
      <div className="flex min-h-svh items-center justify-center bg-background px-4">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle className="text-xl">Check your email</CardTitle>
            <CardDescription>{resendState.message ?? pendingVerify.message}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <form action={verifyAction} className="flex flex-col gap-4">
              <input type="hidden" name="email" value={email} />
              <input type="hidden" name="next" value={next} />
              <div className="flex flex-col gap-2">
                <Label htmlFor="code">6-digit code</Label>
                <Input
                  id="code"
                  name="code"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  placeholder="123456"
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
      </div>
    );
  }

  const activeState = mode === "signin" ? signInState : signUpState;
  const activeAction = mode === "signin" ? signInAction : signUpAction;
  const activePending = mode === "signin" ? signInPending : signUpPending;

  return (
    <div className="flex min-h-svh items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">{mode === "signin" ? "Sign in to Aevrin" : "Create your Aevrin account"}</CardTitle>
          <CardDescription>
            {mode === "signin" ? "Welcome back." : "We'll email you a 6-digit code to verify your address."}
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
              <Input id="email" name="email" type="email" placeholder="you@company.com" required autoFocus />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                name="password"
                type="password"
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
    </div>
  );
}
