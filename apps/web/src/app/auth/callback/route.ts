import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

// OAuth (Google) lands here with a `code` query param after the person
// approves on Google's consent screen — exchanges it for a session, same
// role /auth/confirm plays for the email-code flow.
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next");

  const redirectTo = request.nextUrl.clone();
  redirectTo.pathname = next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
  redirectTo.search = "";

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(redirectTo);
    }
  }

  redirectTo.pathname = "/error";
  return NextResponse.redirect(redirectTo);
}
