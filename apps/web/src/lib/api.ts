"use client";

import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL!;

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = await authHeaders();
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { ...headers, "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Could not reach the Aevrin API. Check your connection and try again.");
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

export const api = {
  createScan: (target_type: string, target: string) =>
    request<import("@/lib/types").Scan>("/scans", {
      method: "POST",
      body: JSON.stringify({ target_type, target }),
    }),
  listScans: () => request<import("@/lib/types").Scan[]>("/scans"),
  getScan: (id: string) => request<import("@/lib/types").Scan>(`/scans/${id}`),
  getScanStages: (id: string) =>
    request<import("@/lib/types").ScanStage[]>(`/scans/${id}/stages`),
  getScanFindings: (id: string) =>
    request<import("@/lib/types").Finding[]>(`/scans/${id}/findings`),
  getFinding: (id: string) => request<import("@/lib/types").Finding>(`/findings/${id}`),
  triageFinding: (id: string, triage_status: string) =>
    request<import("@/lib/types").Finding>(`/findings/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ triage_status }),
    }),
  exportReport: (id: string) => request<{ url: string }>(`/scans/${id}/export`),
  listApiKeys: () => request<import("@/lib/types").ApiKey[]>("/api-keys"),
  createApiKey: (name: string) =>
    request<{ id: number; name: string; plaintext_key: string }>("/api-keys", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  revokeApiKey: (id: number) => request<void>(`/api-keys/${id}`, { method: "DELETE" }),
};
