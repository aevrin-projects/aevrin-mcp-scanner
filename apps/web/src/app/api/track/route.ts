import { createHash } from "node:crypto";
import { type NextRequest, NextResponse } from "next/server";

/**
 * Cookie-free first-party pageview collection.
 *
 * No cookie, no device ID, no localStorage. `visitor_hash` is a salted hash
 * of (IP + user agent + today's date), which counts distinct visitors within
 * a single day and nothing more: the date in the input means yesterday's
 * hash for the same person is a different value, so visits cannot be joined
 * across days, and the hash cannot be reversed to an IP.
 *
 * That is deliberately the weakest identifier that still answers "how many
 * people visited this page today" — it keeps this out of consent-banner
 * territory and means no third-party processor is involved.
 */

const SALT = process.env.ANALYTICS_SALT ?? process.env.API_KEY_PEPPER ?? "aevrin-analytics";

function visitorHash(ip: string, userAgent: string): string {
  const day = new Date().toISOString().slice(0, 10);
  return createHash("sha256").update(`${SALT}:${day}:${ip}:${userAgent}`).digest("hex").slice(0, 32);
}

function coarseDevice(userAgent: string): string {
  const ua = userAgent.toLowerCase();
  if (/ipad|tablet/.test(ua)) return "tablet";
  if (/mobi|android|iphone/.test(ua)) return "mobile";
  return "desktop";
}

export async function POST(request: NextRequest) {
  // Never let analytics failure surface to a visitor: this endpoint always
  // returns 204, whatever happens inside it.
  try {
    const body = (await request.json()) as { path?: string; referrer?: string };
    const path = typeof body.path === "string" ? body.path.slice(0, 512) : null;
    if (!path || !path.startsWith("/")) return new NextResponse(null, { status: 204 });

    // The admin panel is not a page anyone is "visiting" in the marketing
    // sense, and recording founder movement in the same table as customer
    // traffic would only skew it.
    if (path.startsWith("/admin")) return new NextResponse(null, { status: 204 });

    const forwarded = request.headers.get("x-forwarded-for");
    const ip = forwarded ? forwarded.split(",")[0]!.trim() : "unknown";
    const userAgent = request.headers.get("user-agent") ?? "unknown";

    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
    if (!supabaseUrl || !serviceKey) return new NextResponse(null, { status: 204 });

    await fetch(`${supabaseUrl}/rest/v1/page_views`, {
      method: "POST",
      headers: {
        apikey: serviceKey,
        Authorization: `Bearer ${serviceKey}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify({
        path,
        referrer: typeof body.referrer === "string" ? body.referrer.slice(0, 512) || null : null,
        // Railway and Cloudflare both surface this; absent locally.
        country: request.headers.get("cf-ipcountry") ?? request.headers.get("x-vercel-ip-country") ?? null,
        device: coarseDevice(userAgent),
        visitor_hash: visitorHash(ip, userAgent),
      }),
    });
  } catch {
    // Swallowed on purpose — see above.
  }
  return new NextResponse(null, { status: 204 });
}
