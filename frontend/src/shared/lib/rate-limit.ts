// Extra rate limiting on top of whatever Supabase's own auth endpoints
// enforce (explicit product requirement, the email-code step in particular
// is a 6-digit OTP, brute-forceable without a strict attempt limit).
//
// Uses Upstash's REST client (not the TCP+TLS redis-py client backend/api
// uses) since that's the natural fit for Next.js server actions, no
// persistent connection to manage across serverless-style invocations.
// Distinct key namespace (`aevrin:otp:*`) so this can never collide with
// backend/api's `ratelimit:*` / `aevrin:quota:*` keys on the same Redis
// instance.
import { Redis } from "@upstash/redis";

let primary: Redis | null = null;
let fallback: Redis | null | undefined;

function getRedis(): Redis {
  if (!primary) {
    primary = new Redis({
      url: process.env.UPSTASH_REDIS_REST_URL!,
      token: process.env.UPSTASH_REDIS_REST_TOKEN!,
    });
  }
  return primary;
}

/** Spare instance, used only when the primary refuses. Upstash's free tier
 *  caps monthly requests and errors on every command once that ceiling is
 *  hit, which is exactly how sign-in broke. `undefined` means "not yet
 *  resolved"; `null` means "none configured". */
function getFallbackRedis(): Redis | null {
  if (fallback === undefined) {
    const url = process.env.UPSTASH_FALLBACK_REDIS_REST_URL;
    const token = process.env.UPSTASH_FALLBACK_REDIS_REST_TOKEN;
    fallback = url && token ? new Redis({ url, token }) : null;
  }
  return fallback;
}

async function withRedis<T>(op: (client: Redis) => Promise<T>): Promise<T> {
  try {
    return await op(getRedis());
  } catch (error) {
    const spare = getFallbackRedis();
    if (!spare) throw error;
    console.warn("[rate-limit] primary Redis unavailable, using fallback", error);
    return op(spare);
  }
}

export class RateLimitExceededError extends Error {
  constructor(public retryAfterSeconds: number) {
    super("Rate limit exceeded");
  }
}

/** Fixed-window counter: same shape as backend/api's check_fixed_window_rate_limit.
 *
 *  Fails OPEN when Redis itself is unreachable. Every sign-in, sign-up, and
 *  code-verification path funnels through here, so letting an infrastructure
 *  error propagate took authentication down completely: confirmed live when
 *  Upstash hit its request ceiling and every POST /login returned a 500 with
 *  no message a user could act on.
 *
 *  The residual risk is bounded and accepted. This limiter exists to slow
 *  brute-forcing of the 6-digit email OTP, but it was only ever a second
 *  layer, Supabase enforces its own limits on the same auth endpoints, and
 *  those are unaffected by our Redis being down. Trading a strictly weaker
 *  second layer during an outage for "nobody can log in at all" is not a
 *  trade worth making.
 */
export async function checkRateLimit(key: string, limit: number, windowSeconds: number): Promise<void> {
  const redisKey = `aevrin:otp:${key}`;
  let current: number;
  try {
    current = await withRedis(async (redis) => {
      const value = await redis.incr(redisKey);
      if (value === 1) await redis.expire(redisKey, windowSeconds);
      return value;
    });
  } catch (error) {
    console.warn("[rate-limit] Redis unavailable, allowing auth attempt through", error);
    return;
  }

  if (current > limit) {
    let ttl = windowSeconds;
    try {
      const fresh = await withRedis((redis) => redis.ttl(redisKey));
      if (fresh > 0) ttl = fresh;
    } catch {
      // Keep the nominal window, the limit itself already tripped, and a
      // failed TTL read must not turn a clean 429 into a 500.
    }
    throw new RateLimitExceededError(ttl);
  }
}
