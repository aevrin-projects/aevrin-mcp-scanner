import { BrandIcon } from "@/shared/ui/brand-icon";

export type ProviderKey = "groq" | "openai" | "anthropic" | "gemini";

/** The four vendors `integrations/ai_providers.py` supports, with its labels. */
export const PROVIDERS: { key: ProviderKey; label: string }[] = [
  { key: "groq", label: "Groq" },
  { key: "openai", label: "OpenAI" },
  { key: "anthropic", label: "Anthropic" },
  { key: "gemini", label: "Google Gemini" },
];

export function ProviderMark({ provider, className = "size-4" }: { provider: ProviderKey; className?: string }) {
  // Groq's mark is a filled square; the small radius matches the other tiles.
  return <BrandIcon name={provider} className={provider === "groq" ? `overflow-hidden rounded-[3px] ${className}` : className} />;
}
