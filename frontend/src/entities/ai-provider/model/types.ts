/**
 * AI provider domain types.
 *
 * There is no `apiKey` field anywhere in this file, and there must never be
 * one. The API does not return keys, so the client has nothing to hold; a
 * type that could express a stored key would be an invitation to put one in
 * React state, where it would end up in a serialised RSC payload or a devtools
 * snapshot.
 */

export type ProviderKey = "groq" | "gemini" | "anthropic" | "openai";

export type ModelStatus = "active" | "deprecated" | "unavailable";

export interface ProviderCredential {
  provider: ProviderKey;
  label: string;
  consoleUrl: string | null;
  docsUrl: string | null;
  /** Whether a key is stored. Never the key. */
  keyPresent: boolean;
  /** Last four characters, to tell two keys apart. Nothing more. */
  keyHint: string;
  modelId: string | null;
  temperature: number | null;
  maxTokens: number | null;
  systemPrompt: string | null;
  /** 1 is the primary; higher numbers are fallbacks tried in order. */
  priority: number;
  enabled: boolean;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface ProviderModel {
  provider: ProviderKey;
  modelId: string;
  displayName: string;
  status: ModelStatus;
  contextWindow: number | null;
  maxOutputTokens: number | null;
  documentationUrl: string | null;
  lastCheckedAt: string | null;
}

export interface ProviderStatus {
  provider: ProviderKey;
  label: string;
  consoleUrl: string | null;
  docsUrl: string | null;
  /** Whether Aevrin holds its own credential for refreshing this catalogue.
   *  Its absence is the usual reason a model list is empty. */
  catalogCredentialConfigured: boolean;
  activeModels: number;
  lastSuccessfulSync: string | null;
  lastAttemptedSync: string | null;
  syncError: string | null;
  healthy: boolean;
}

/**
 * An AI explanation.
 *
 * `provider` and `model` are non-optional because the reader must always be
 * able to see which vendor produced this. Fallback can change it between one
 * request and the next, and an explanation is a different kind of claim from
 * a verified finding — it has to be attributable and labelled as such.
 */
export interface Explanation {
  available: true;
  summary: string;
  detail: string | null;
  provider: string;
  modelId: string;
  cached: boolean;
  createdAt: string | null;
}

export interface ExplanationUnavailable {
  available: false;
  reason: string;
}

export type ExplanationResult = Explanation | ExplanationUnavailable;

export type ExplainSubject =
  | "finding"
  | "trust_grade"
  | "agent_posture"
  | "permission"
  | "skill"
  | "attack_path"
  | "scan"
  | "listing";

export const PROVIDER_LABELS: Record<ProviderKey, string> = {
  groq: "Groq",
  gemini: "Google Gemini",
  anthropic: "Anthropic",
  openai: "OpenAI",
};

/**
 * Where to get a key. Links only — Aevrin makes no claim about what any of
 * these cost. Free tiers and rate limits change without notice, and telling
 * someone an API was free when it had started charging would be a real
 * problem created for no benefit.
 */
export const PROVIDER_CONSOLES: Record<ProviderKey, string> = {
  groq: "https://console.groq.com/keys",
  gemini: "https://aistudio.google.com/apikey",
  anthropic: "https://console.anthropic.com/settings/keys",
  openai: "https://platform.openai.com/api-keys",
};
