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

/** Fixed-window counter — same shape as apps/api's check_fixed_window_rate_limit. */
export async function checkRateLimit(key: string, limit: number, windowSeconds: number): Promise<void> {
  const redisKey = `aevrin:otp:${key}`;
  const redis = getRedis();
  const current = await redis.incr(redisKey);
  if (current === 1) {
    await redis.expire(redisKey, windowSeconds);
  }
  if (current > limit) {
    const ttl = await redis.ttl(redisKey);
    throw new RateLimitExceededError(ttl > 0 ? ttl : windowSeconds);
  }
}
