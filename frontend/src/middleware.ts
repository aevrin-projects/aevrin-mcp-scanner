import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/shared/lib/supabase/proxy";

// Next 16 renamed this file to proxy.ts, but a proxy is pinned to the Node.js
// runtime and the runtime option throws if you set it. @opennextjs/cloudflare
// compiles to a Worker and refuses a Node.js middleware outright ("Node.js
// middleware is not currently supported"), so deploying to Cloudflare means
// staying on the deprecated middleware convention, which still defaults to the
// edge runtime. Revisit when Next ships edge instructions for proxy.

// docs.mcp.aevrin.net serves the same fumadocs pages as /docs on the apex,
// rewritten rather than redirected, so mcp.aevrin.net/docs/* stays canonical
// and every published link keeps working.
const DOCS_HOST = "docs.mcp.aevrin.net";

export async function middleware(request: NextRequest) {
  const host = (request.headers.get("host") ?? "").split(":")[0].toLowerCase();

  if (host === DOCS_HOST) {
    const { pathname } = request.nextUrl;
    // Docs are public, so the session work below is skipped entirely. It would
    // also misfire here: a signed-in visitor hitting "/" gets bounced to
    // /dashboard, which is right on the apex and wrong on this subdomain.
    if (pathname.startsWith("/api/") || pathname.startsWith("/_next/") || pathname.startsWith("/docs")) {
      return NextResponse.next();
    }
    const url = request.nextUrl.clone();
    url.pathname = pathname === "/" ? "/docs" : `/docs${pathname}`;
    return NextResponse.rewrite(url);
  }

  return await updateSession(request);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
