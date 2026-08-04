import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

// Built from NEXT_PUBLIC_SITE_URL rather than request.nextUrl — behind
// Railway's proxy, request.nextUrl's origin resolves to the container's own
// bind address (localhost:8080) instead of the public Host header, which
// sent every post-login redirect to a dead localhost URL.
const siteUrl = () => process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

// OAuth (Google or GitHub) lands here with a `code` query param after the
// person approves on the provider's consent screen — exchanges it for a
// session, same role /auth/confirm plays for the email-code flow.
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next");
  const path = next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";

  // The provider appends its own error instead of a code when the person
  // denies consent or the request itself was malformed — surfacing which
  // one happened beats dumping every failure on the same generic error
  // page. `provider` is our own query param (see signInWithGithub), not
  // something either OAuth provider sets.
  const providerError = searchParams.get("error");
  if (providerError) {
    const provider = searchParams.get("provider") === "github" ? "github" : "google";
    const reason = providerError === "access_denied" ? `${provider}_denied` : `${provider}_error`;
    return NextResponse.redirect(new URL(`/error?reason=${reason}`, siteUrl()));
  }

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(new URL(path, siteUrl()));
    }
    return NextResponse.redirect(new URL("/error?reason=exchange_failed", siteUrl()));
  }

  return NextResponse.redirect(new URL("/error?reason=missing_code", siteUrl()));
}
