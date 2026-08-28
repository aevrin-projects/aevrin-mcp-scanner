import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/shared/lib/supabase/proxy";

// Next 16 renamed this file to proxy.ts, but a proxy is pinned to the Node.js
// runtime and the runtime option throws if you set it. @opennextjs/cloudflare
// compiles to a Worker and refuses a Node.js middleware outright ("Node.js
// middleware is not currently supported"), so deploying to Cloudflare means
// staying on the deprecated middleware convention, which still defaults to the
// edge runtime. Revisit when Next ships edge instructions for proxy.

// docs.mcp.aevrin.net is its own Cloudflare Worker (frontend-docs/) as of the
// split recorded in DECISIONS.md -- fumadocs/MDX rendering no longer lives in
// this app's bundle at all. A published /docs/* link on the apex still needs
// to resolve, so it's redirected rather than rewritten; there is nothing left
// here to rewrite to.
export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname === "/docs" || pathname.startsWith("/docs/")) {
    const target = new URL(`https://docs.mcp.aevrin.net${pathname.slice("/docs".length)}`);
    target.search = request.nextUrl.search;
    return NextResponse.redirect(target, 308);
  }

  return await updateSession(request);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
