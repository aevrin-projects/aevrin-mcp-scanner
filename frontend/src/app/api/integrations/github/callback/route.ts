import { NextResponse, type NextRequest } from "next/server";

// The aevrin-mcp-security GitHub App's Callback URL is configured to this
// path on the primary domain rather than the API's own origin; this
// route exists purely to bounce the browser on to the real handler
// (GET /github/callback on the API), forwarding every query param GitHub
// sent (code, installation_id, setup_action, state) unchanged. All the
// actual logic, verifying state, resolving the installation, upserting
// github_installations; lives once, in the API, not duplicated here.
export async function GET(request: NextRequest) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) {
    return NextResponse.redirect(new URL("/dashboard/settings?github=error", request.url));
  }
  const target = new URL("/github/callback", apiUrl);
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.set(key, value));
  return NextResponse.redirect(target);
}
