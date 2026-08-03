import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

// /device is reachable pre-auth so an unauthenticated visit redirects into
// the normal /login flow with a return path, rather than a bare 404 — see
// the /device page itself for the post-login redirect back. The rest are
// the public marketing site (landing, pricing, legal, status) — the
// actual app lives under explicit protected prefixes. Unknown routes pass
// through to Next's real 404 instead of being disguised as login pages.
const PUBLIC_PATHS_EXACT = ["/"];
const PUBLIC_PATH_PREFIXES = ["/login", "/auth", "/device", "/pricing", "/terms", "/privacy", "/status", "/error"];
const PROTECTED_PATH_PREFIXES = ["/dashboard", "/scans", "/settings", "/integrations", "/usage"];

function matchesPath(pathname: string, prefix: string) {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

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
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options),
          );
          Object.entries(headers).forEach(([key, value]) =>
            supabaseResponse.headers.set(key, value),
          );
        },
      },
    },
  );

  // Do not run code between createServerClient and getClaims() — see
  // Supabase's SSR docs: skipping this call can randomly log users out.
  const { data } = await supabase.auth.getClaims();
  const user = data?.claims;

  const { pathname } = request.nextUrl;
  const isPublicPath =
    PUBLIC_PATHS_EXACT.includes(pathname) || PUBLIC_PATH_PREFIXES.some((path) => matchesPath(pathname, path));
  const isProtectedPath = PROTECTED_PATH_PREFIXES.some((path) => matchesPath(pathname, path));

  if (!user && !isPublicPath && isProtectedPath) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}
