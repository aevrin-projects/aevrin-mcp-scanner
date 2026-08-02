"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { checkRateLimit, RateLimitExceededError } from "@/lib/rate-limit";

export type LoginState = {
  status: "idle" | "verify-code" | "google-only" | "error";
  message?: string;
  email?: string;
  mode?: "signin" | "signup";
};

export type ResetState = {
  status: "idle" | "code-sent" | "error" | "done";
  message?: string;
  email?: string;
};

const siteUrl = () => process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
const apiUrl = () => process.env.NEXT_PUBLIC_API_URL!;

type AccountLookup = { exists: boolean; providers: string[]; has_password: boolean };

// Backed by a service-role-only Postgres function (see
// infra/migrations/0004_account_lookup_function.sql) — Supabase auto-links
// identities across providers for the same email, so telling "no account"
// apart from "account exists via Google, no password set" needs to read
// auth.identities, which the anon key can't reach directly.
async function lookupAccount(email: string): Promise<AccountLookup> {
  try {
    const res = await fetch(`${apiUrl()}/auth/lookup?email=${encodeURIComponent(email)}`, {
      cache: "no-store",
    });
    if (!res.ok) return { exists: false, providers: [], has_password: false };
    return (await res.json()) as AccountLookup;
  } catch {
    return { exists: false, providers: [], has_password: false };
  }
}

// Only ever redirect to a relative, in-app path — formData is
// user-controlled, and an unvalidated redirect target is an open-redirect
// vector (never accept a full URL / protocol-relative "//" path here).
function safeNext(formData: FormData): string {
  const next = formData.get("next");
  if (typeof next === "string" && next.startsWith("/") && !next.startsWith("//") && next !== "/") {
    return next;
  }
  return "/dashboard";
}

export async function signInWithGoogle(formData: FormData): Promise<void> {
  const next = safeNext(formData);
  const supabase = await createClient();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: `${siteUrl()}/auth/callback?next=${encodeURIComponent(next)}`,
      skipBrowserRedirect: true,
    },
  });
  if (error || !data.url) {
    // Nothing sensible to return to the caller — signInWithGoogle is a
    // plain <form action> with no useActionState wired to it, so surface
    // failure the same way redirect() would: throw and let Next's default
    // error boundary handle a genuinely broken OAuth config.
    throw new Error(error?.message ?? "Could not start Google sign-in.");
  }
  redirect(data.url);
}

export async function signInWithPassword(_prevState: LoginState, formData: FormData): Promise<LoginState> {
  const email = (formData.get("email") as string) ?? "";
  const password = (formData.get("password") as string) ?? "";
  if (!email || !password) {
    return { status: "error", message: "Enter your email and password.", mode: "signin" };
  }

  try {
    await checkRateLimit(`verify:${email}`, 10, 900);
  } catch (err) {
    if (err instanceof RateLimitExceededError) {
      return { status: "error", message: "Too many attempts. Try again in a few minutes.", mode: "signin" };
    }
    throw err;
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) {
    const lookup = await lookupAccount(email);
    if (lookup.exists && !lookup.has_password) {
      return {
        status: "google-only",
        email,
        mode: "signin",
        message: "This email signed in with Google and doesn't have a password yet.",
      };
    }
    return { status: "error", message: "Incorrect email or password.", mode: "signin" };
  }
  redirect(safeNext(formData));
}

export async function signUpWithPassword(_prevState: LoginState, formData: FormData): Promise<LoginState> {
  const email = (formData.get("email") as string) ?? "";
  const password = (formData.get("password") as string) ?? "";
  if (!email || !password) {
    return { status: "error", message: "Enter an email and password.", mode: "signup" };
  }
  if (password.length < 8) {
    return { status: "error", message: "Password must be at least 8 characters.", mode: "signup" };
  }

  try {
    await checkRateLimit(`request:${email}`, 5, 3600);
  } catch (err) {
    if (err instanceof RateLimitExceededError) {
      return { status: "error", message: "Too many signup attempts. Try again in a bit.", mode: "signup" };
    }
    throw err;
  }

  // Checked before calling signUp() rather than relying on GoTrue's
  // anti-enumeration "fake success, no email sent" response for already-
  // confirmed users — that silent success left people staring at a "check
  // your email" screen for a code that would never arrive.
  const lookup = await lookupAccount(email);
  if (lookup.exists) {
    const viaGoogle = lookup.providers.includes("google") && !lookup.has_password;
    return {
      status: "error",
      mode: "signup",
      message: viaGoogle
        ? "An account with this email already exists — you signed in with Google. Sign in with Google, or use \"Forgot password\" to set one."
        : "An account with this email already exists. Try signing in instead.",
    };
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.signUp({ email, password });
  if (error) {
    return { status: "error", message: error.message, mode: "signup" };
  }
  return { status: "verify-code", email, mode: "signup", message: `We emailed a code to ${email}.` };
}

export async function verifySignupCode(_prevState: LoginState, formData: FormData): Promise<LoginState> {
  const email = (formData.get("email") as string) ?? "";
  const code = (formData.get("code") as string) ?? "";
  if (!email || !code) {
    return { status: "verify-code", email, mode: "signup", message: "Enter the code from your email." };
  }

  try {
    // The guess-limit — this is the one that actually matters, since a
    // 6-digit code has only a million possibilities.
    await checkRateLimit(`verify:${email}`, 5, 900);
  } catch (err) {
    if (err instanceof RateLimitExceededError) {
      return { status: "error", message: "Too many incorrect attempts. Request a new code and try again." };
    }
    throw err;
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.verifyOtp({ email, token: code, type: "signup" });
  if (error) {
    return { status: "verify-code", email, mode: "signup", message: "That code is incorrect or expired." };
  }
  redirect(safeNext(formData));
}

export async function resendSignupCode(_prevState: LoginState, formData: FormData): Promise<LoginState> {
  const email = (formData.get("email") as string) ?? "";
  try {
    await checkRateLimit(`request:${email}`, 5, 3600);
  } catch (err) {
    if (err instanceof RateLimitExceededError) {
      return { status: "verify-code", email, mode: "signup", message: "Too many resend attempts. Try again later." };
    }
    throw err;
  }
  const supabase = await createClient();
  const { error } = await supabase.auth.resend({ type: "signup", email });
  if (error) {
    return { status: "verify-code", email, mode: "signup", message: error.message };
  }
  return { status: "verify-code", email, mode: "signup", message: `Sent a new code to ${email}.` };
}

// --- Forgot password: same rate-limited code pattern as signup, but the
// code both verifies identity (type: 'recovery') and immediately gates a
// new-password submission — Supabase's verifyOtp for 'recovery' establishes
// a real session, which updateUser({ password }) then uses.

export async function requestPasswordReset(_prevState: ResetState, formData: FormData): Promise<ResetState> {
  const email = (formData.get("email") as string) ?? "";
  if (!email) {
    return { status: "error", message: "Enter your email address." };
  }

  try {
    await checkRateLimit(`request:${email}`, 5, 3600);
  } catch (err) {
    if (err instanceof RateLimitExceededError) {
      return { status: "error", message: "Too many reset attempts. Try again in a bit.", email };
    }
    throw err;
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.resetPasswordForEmail(email);
  if (error) {
    return { status: "error", message: error.message, email };
  }
  return { status: "code-sent", email, message: `We emailed a code to ${email}.` };
}

export async function resendPasswordResetCode(_prevState: ResetState, formData: FormData): Promise<ResetState> {
  const email = (formData.get("email") as string) ?? "";
  try {
    await checkRateLimit(`request:${email}`, 5, 3600);
  } catch (err) {
    if (err instanceof RateLimitExceededError) {
      return { status: "code-sent", email, message: "Too many resend attempts. Try again later." };
    }
    throw err;
  }
  const supabase = await createClient();
  const { error } = await supabase.auth.resetPasswordForEmail(email);
  if (error) {
    return { status: "code-sent", email, message: error.message };
  }
  return { status: "code-sent", email, message: `Sent a new code to ${email}.` };
}

export async function verifyPasswordResetCode(_prevState: ResetState, formData: FormData): Promise<ResetState> {
  const email = (formData.get("email") as string) ?? "";
  const code = (formData.get("code") as string) ?? "";
  const newPassword = (formData.get("newPassword") as string) ?? "";
  if (!email || !code || !newPassword) {
    return { status: "code-sent", email, message: "Enter the code and a new password." };
  }
  if (newPassword.length < 8) {
    return { status: "code-sent", email, message: "Password must be at least 8 characters." };
  }

  try {
    // The guess-limit on the code itself — same reasoning as signup: a
    // 6-digit code is brute-forceable without a strict attempt cap.
    await checkRateLimit(`verify:${email}`, 5, 900);
  } catch (err) {
    if (err instanceof RateLimitExceededError) {
      return { status: "error", message: "Too many incorrect attempts. Request a new code and try again." };
    }
    throw err;
  }

  const supabase = await createClient();
  const { error: verifyError } = await supabase.auth.verifyOtp({ email, token: code, type: "recovery" });
  if (verifyError) {
    return { status: "code-sent", email, message: "That code is incorrect or expired." };
  }

  const { error: updateError } = await supabase.auth.updateUser({ password: newPassword });
  if (updateError) {
    return { status: "code-sent", email, message: updateError.message };
  }

  redirect("/dashboard");
}
