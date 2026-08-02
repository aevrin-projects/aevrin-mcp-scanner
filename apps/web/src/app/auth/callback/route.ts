import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

// Built from NEXT_PUBLIC_SITE_URL rather than request.nextUrl — behind
// Railway's proxy, request.nextUrl's origin resolves to the container's own
// bind address (localhost:8080) instead of the public Host header, which
// sent every post-login redirect to a dead localhost URL.
const siteUrl = () => process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

// OAuth (Google) lands here with a `code` query param after the person
// approves on Google's consent screen — exchanges it for a session, same
// role /auth/confirm plays for the email-code flow.
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next");
  const path = next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(new URL(path, siteUrl()));
    }
  }

  return NextResponse.redirect(new URL("/error", siteUrl()));
}
