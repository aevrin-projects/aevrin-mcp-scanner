// Extra rate limiting on top of whatever Supabase's own auth endpoints
// enforce (explicit product requirement — the email-code step in particular
// is a 6-digit OTP, brute-forceable without a strict attempt limit).
//
// Uses Upstash's REST client (not the TCP+TLS redis-py client apps/api
// uses) since that's the natural fit for Next.js server actions — no
// persistent connection to manage across serverless-style invocations.
// Distinct key namespace (`aevrin:otp:*`) so this can never collide with
// apps/api's `ratelimit:*` / `aevrin:quota:*` keys on the same Redis
// instance.

import { Redis } from "@upstash/redis";

let client: Redis | null = null;

function getRedis(): Redis {
  if (!client) {
    client = new Redis({
      url: process.env.UPSTASH_REDIS_REST_URL!,
      token: process.env.UPSTASH_REDIS_REST_TOKEN!,
    });
  }
  return client;
}

export class RateLimitExceededError extends Error {
  constructor(public retryAfterSeconds: number) {
    super("Rate limit exceeded");
  }
}

/** Fixed-window counter — same shape as apps/api's check_fixed_window_rate_limit.
 *
 *  Fails OPEN when Redis itself is unreachable. Every sign-in, sign-up, and
 *  code-verification path funnels through here, so letting an infrastructure
 *  error propagate took authentication down completely: confirmed live when
 *  Upstash hit its request ceiling and every POST /login returned a 500 with
 *  no message a user could act on.
 *
 *  The residual risk is bounded and accepted. This limiter exists to slow
 *  brute-forcing of the 6-digit email OTP, but it was only ever a second
 *  layer — Supabase enforces its own limits on the same auth endpoints, and
 *  those are unaffected by our Redis being down. Trading a strictly weaker
 *  second layer during an outage for "nobody can log in at all" is not a
 *  trade worth making.
 */
export async function checkRateLimit(key: string, limit: number, windowSeconds: number): Promise<void> {
  const redisKey = `aevrin:otp:${key}`;
  let current: number;
  try {
    const redis = getRedis();
    current = await redis.incr(redisKey);
    if (current === 1) {
      await redis.expire(redisKey, windowSeconds);
    }
  } catch (error) {
    console.warn("[rate-limit] Redis unavailable, allowing auth attempt through", error);
    return;
  }

  if (current > limit) {
    let ttl = windowSeconds;
    try {
      const fresh = await getRedis().ttl(redisKey);
      if (fresh > 0) ttl = fresh;
    } catch {
      // Keep the nominal window — the limit itself already tripped, and a
      // failed TTL read must not turn a clean 429 into a 500.
    }
    throw new RateLimitExceededError(ttl);
  }
}
