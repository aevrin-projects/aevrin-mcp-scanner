"use client";

import { createClient } from "@/shared/lib/supabase/client";

export const API_URL = process.env.NEXT_PUBLIC_API_URL!;

const UNREACHABLE = "Could not reach the Aevrin API. Check your connection and try again.";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function authHeaders(): Promise<Record<string, string>> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) {
    throw new ApiError(401, "Not signed in");
  }
  return { Authorization: `Bearer ${session.access_token}` };
}

async function send<T>(path: string, init: RequestInit | undefined, headers: Record<string, string>): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { ...headers, "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, UNREACHABLE);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // non-JSON error body, fall back to statusText
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Authenticated call. Throws 401 before hitting the network when signed out. */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return send<T>(path, init, await authHeaders());
}

/** Same handling without requiring a session, for anything a signed-out
 *  visitor can see. `authHeaders` throws when signed out, which is right for
 *  account endpoints and wrong for public ones. */
export async function publicRequest<T>(path: string, init?: RequestInit): Promise<T> {
  return send<T>(path, init, {});
}

/**
 * Public to read, but personalised when there is somebody to personalise for.
 *
 * The mirror of the API's own `optional_user` dependency, and the missing
 * third case: `request` refuses to send anything while signed out, and
 * `publicRequest` refuses to send credentials even when they exist. A route
 * that is readable anonymously *and* returns a per-user field had no correct
 * client for it, so the marketplace used `publicRequest` and every listing
 * came back with `is_favorited: false` -- saving worked and then looked like
 * it had not, because the read that would have shown it was anonymous.
 */
export async function optionalAuthRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return send<T>(
    path,
    init,
    session ? { Authorization: `Bearer ${session.access_token}` } : {},
  );
}
