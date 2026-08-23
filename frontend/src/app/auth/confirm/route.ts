import { type EmailOtpType } from "@supabase/supabase-js";
import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/shared/lib/supabase/server";

// See auth/callback/route.ts: built from NEXT_PUBLIC_SITE_URL, not
// request.nextUrl, for the same reason (its origin resolves to the
// container's internal bind address behind a load balancer).
const siteUrl = () => process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const token_hash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;

  if (token_hash && type) {
    const supabase = await createClient();
    const { error } = await supabase.auth.verifyOtp({ type, token_hash });
    if (!error) {
      return NextResponse.redirect(new URL("/onboarding", siteUrl()));
    }
    return NextResponse.redirect(new URL("/error?reason=exchange_failed", siteUrl()));
  }

  return NextResponse.redirect(new URL("/error?reason=missing_code", siteUrl()));
}
