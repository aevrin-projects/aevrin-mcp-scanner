"use client";

import { request } from "@/shared/api";
import type {
  ExplainSubject,
  ExplanationResult,
  ProviderCredential,
  ProviderKey,
  ProviderModel,
} from "../model/types";

/**
 * AI provider transport.
 *
 * `saveProvider` is the only function that ever sends a key, and it sends it
 * once, outbound. Nothing here reads one back, because the API has no endpoint
 * that returns one.
 */

function toCredential(raw: Record<string, unknown>): ProviderCredential {
  return {
    provider: raw.provider as ProviderKey,
    label: String(raw.label ?? raw.provider),
    consoleUrl: (raw.console_url as string) ?? null,
    docsUrl: (raw.docs_url as string) ?? null,
    keyPresent: Boolean(raw.key_present),
    keyHint: String(raw.key_hint ?? ""),
    modelId: (raw.model_id as string) ?? null,
    temperature: (raw.temperature as number) ?? null,
    maxTokens: (raw.max_tokens as number) ?? null,
    systemPrompt: (raw.system_prompt as string) ?? null,
    priority: Number(raw.priority ?? 1),
    enabled: raw.enabled !== false,
    createdAt: (raw.created_at as string) ?? null,
    updatedAt: (raw.updated_at as string) ?? null,
  };
}

export async function listProviders(): Promise<ProviderCredential[]> {
  const raw = await request<Record<string, unknown>[]>("/ai/providers");
  return raw.map(toCredential);
}

export async function saveProvider(input: {
  provider: ProviderKey;
  apiKey: string;
  modelId?: string | null;
  temperature?: number | null;
  maxTokens?: number | null;
  systemPrompt?: string | null;
  priority?: number;
}): Promise<ProviderCredential> {
  const raw = await request<Record<string, unknown>>("/ai/providers", {
    method: "PUT",
    body: JSON.stringify({
      provider: input.provider,
      api_key: input.apiKey,
      model_id: input.modelId ?? null,
      temperature: input.temperature ?? null,
      max_tokens: input.maxTokens ?? null,
      system_prompt: input.systemPrompt ?? null,
      priority: input.priority ?? 1,
    }),
  });
  return toCredential(raw);
}

export async function updateProvider(
  provider: ProviderKey,
  patch: {
    modelId?: string | null;
    temperature?: number | null;
    maxTokens?: number | null;
    systemPrompt?: string | null;
    priority?: number;
    enabled?: boolean;
  },
): Promise<ProviderCredential> {
  const body: Record<string, unknown> = {};
  if (patch.modelId !== undefined) body.model_id = patch.modelId;
  if (patch.temperature !== undefined) body.temperature = patch.temperature;
  if (patch.maxTokens !== undefined) body.max_tokens = patch.maxTokens;
  if (patch.systemPrompt !== undefined) body.system_prompt = patch.systemPrompt;
  if (patch.priority !== undefined) body.priority = patch.priority;
  if (patch.enabled !== undefined) body.enabled = patch.enabled;

  const raw = await request<Record<string, unknown>>(`/ai/providers/${provider}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  return toCredential(raw);
}

export async function deleteProvider(provider: ProviderKey): Promise<void> {
  await request(`/ai/providers/${provider}`, { method: "DELETE" });
}

export async function listModels(provider?: ProviderKey): Promise<ProviderModel[]> {
  const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
  const raw = await request<Record<string, unknown>[]>(`/ai/models${query}`);
  return raw.map((m) => ({
    provider: m.provider as ProviderKey,
    modelId: String(m.model_id),
    displayName: String(m.display_name),
    status: m.status as ProviderModel["status"],
    contextWindow: (m.context_window as number) ?? null,
    maxOutputTokens: (m.max_output_tokens as number) ?? null,
    documentationUrl: (m.documentation_url as string) ?? null,
    lastCheckedAt: (m.last_checked_at as string) ?? null,
  }));
}

export async function explain(input: {
  subjectType: ExplainSubject;
  subjectId: string;
  detailed?: boolean;
  refresh?: boolean;
}): Promise<ExplanationResult> {
  const raw = await request<Record<string, unknown>>("/ai/explain", {
    method: "POST",
    body: JSON.stringify({
      subject_type: input.subjectType,
      subject_id: input.subjectId,
      detailed: input.detailed ?? false,
      refresh: input.refresh ?? false,
    }),
  });

  // The API answers 200 with `available: false` when no provider could
  // respond. That is not an error: the finding being explained is unaffected,
  // and treating it as a failure would make an AI outage look like a scanner
  // outage.
  if (raw.available === false) {
    return { available: false, reason: String(raw.reason ?? "AI explanation unavailable.") };
  }

  return {
    available: true,
    summary: String(raw.summary ?? ""),
    detail: (raw.detail as string) ?? null,
    provider: String(raw.provider ?? ""),
    modelId: String(raw.model_id ?? ""),
    cached: Boolean(raw.cached),
    createdAt: (raw.created_at as string) ?? null,
  };
}
