import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

// /device is reachable pre-auth so an unauthenticated visit redirects into
// the normal /login flow with a return path, rather than a bare 404; see
// the /device page itself for the post-login redirect back. The rest are
// the public marketing site (landing, pricing, docs, legal, status), the
// actual app lives under explicit protected prefixes. Unknown routes pass
// through to Next's real 404 instead of being disguised as login pages.
const PUBLIC_PATHS_EXACT = ["/"];
const PUBLIC_PATH_PREFIXES = ["/login", "/auth", "/device", "/pricing", "/docs", "/terms", "/privacy", "/status", "/error"];
const PROTECTED_PATH_PREFIXES = ["/dashboard", "/onboarding", "/scans", "/settings", "/integrations", "/usage", "/admin", "/agents"];

function matchesPath(pathname: string, prefix: string) {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

// This is the ONLY place in the app that should ever call getClaims()
// server-side. Every page previously re-derived auth state itself
// (layout.tsx, page.tsx, device/page.tsx each ran their own getClaims()),
// which meant a single page load could trigger 2-3 independent refresh
// attempts against the same refresh token. Supabase only tolerates reusing
// a refresh token within a 10-second grace window (see "What is refresh
// token reuse detection" in Supabase's docs), outside that window, reuse
// is treated as theft and the *entire* session is revoked. That's what was
// causing people to get logged out and have to sign in again repeatedly:
// confirmed live in the project's auth logs, which showed token_refreshed
// and token_revoked firing in the same second, followed by "Invalid Refresh
// Token: Refresh Token Not Found" and a forced /logout. The fix is to
// resolve identity exactly once here and hand it to every Server Component
// via a request header; see layout.tsx/page.tsx/device/page.tsx, which now
// read x-aevrin-user-email/x-aevrin-user-id instead of calling Supabase
// again.
export async function updateSession(request: NextRequest) {
  const cookiesToApply: { name: string; value: string; options?: Record<string, unknown> }[] = [];
  let cacheHeaders: Record<string, string> = {};

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet, headers) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          cookiesToApply.push(...cookiesToSet);
          cacheHeaders = headers;
        },
      },
    },
  );

  // Do not run code between createServerClient and getClaims(); see
  // Supabase's SSR docs: skipping this call can randomly log users out.
  const { data } = await supabase.auth.getClaims();
  const user = data?.claims;

  // Per Next.js's documented pattern for forwarding request headers to
  // Server Components: NextResponse.next({ request: { headers } }) with a
  // fresh Headers clone; not NextResponse.next({ headers }) (that sets
  // *response* headers, visible to the browser, not request headers) and
  // not passing the NextRequest itself (untyped for this purpose, even
  // though request.cookies mutation below relies on the same object).
  const requestHeaders = new Headers(request.headers);
  if (user) {
    requestHeaders.set("x-aevrin-user-id", String(user.sub ?? ""));
    requestHeaders.set("x-aevrin-user-email", String(user.email ?? ""));
  } else {
    requestHeaders.delete("x-aevrin-user-id");
    requestHeaders.delete("x-aevrin-user-email");
  }

  const { pathname } = request.nextUrl;
  const isPublicPath =
    PUBLIC_PATHS_EXACT.includes(pathname) || PUBLIC_PATH_PREFIXES.some((path) => matchesPath(pathname, path));
  const isProtectedPath = PROTECTED_PATH_PREFIXES.some((path) => matchesPath(pathname, path));

  if (!user && !isPublicPath && isProtectedPath) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  // A signed-in person landing on the marketing root or the login page is
  // almost always trying to get back into the product; send them there
  // instead of making them re-navigate (and re-authenticate) by hand. The
  // rest of the marketing site (/pricing, /docs, /terms…) stays reachable
  // while signed in, since those are genuinely still useful.
  if (user && (pathname === "/" || pathname === "/login")) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    url.search = "";
    return NextResponse.redirect(url);
  }

  // Exactly one response, built once, after the header decision above;
  // carries the refreshed cookies (browser) and the identity header
  // (downstream Server Components) together, instead of the previous
  // pattern of rebuilding a response inline inside setAll every time a
  // cookie changed.
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  cookiesToApply.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
  Object.entries(cacheHeaders).forEach(([key, value]) => response.headers.set(key, value));
  return response;
}
