"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Loader2, Trash2 } from "lucide-react";

import {
  PROVIDER_CONSOLES,
  PROVIDER_LABELS,
  deleteProvider,
  listModels,
  listProviders,
  saveProvider,
  updateProvider,
  type ProviderCredential,
  type ProviderKey,
  type ProviderModel,
} from "@/entities/ai-provider";
import { ApiError } from "@/shared/api";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { PageHeader, Panel, PanelBody, PanelHeader, PanelTitle, Select } from "@/shared/ui";

/**
 * Settings → AI providers.
 *
 * The key input is write-only. Once saved, the field clears and what remains
 * on screen is "key ending 4f2a". There is no view, no reveal, and no request
 * that could fetch it back — the API has no endpoint that returns a key, so
 * this page could not display one even if it tried.
 *
 * Models come from Aevrin's own synced catalogue rather than a list compiled
 * here. That is the whole point of the catalogue: when a vendor ships a new
 * model, it appears in these dropdowns without anyone editing the frontend.
 *
 * Nothing on this page claims any provider is free. Free tiers change, and a
 * security tool that told someone an API cost nothing when it had started
 * charging would have created a real problem for no benefit.
 */

const PROVIDERS: ProviderKey[] = ["groq", "gemini", "anthropic", "openai"];

export function AiProvidersPage() {
  const [credentials, setCredentials] = useState<ProviderCredential[]>([]);
  const [models, setModels] = useState<ProviderModel[]>([]);
  const [loading, setLoading] = useState(true);

  // Bumped by a child card after it saves, which re-runs the effect below.
  // Refreshing through a counter rather than by calling a shared setter keeps
  // every state update inside an async continuation, where React wants it.
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [creds, catalog] = await Promise.all([
        listProviders().catch(() => [] as ProviderCredential[]),
        listModels().catch(() => [] as ProviderModel[]),
      ]);
      if (cancelled) return;
      setCredentials(creds);
      setModels(catalog);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="size-5 animate-spin text-muted-foreground" aria-hidden="true" />
        <span className="sr-only">Loading</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI providers"
        description="Configure a provider to get plain-language explanations of security findings."
      />

      <Panel>
        <PanelBody>
          <p className="text-sm text-muted-foreground">
            AI explanations interpret evidence Aevrin&apos;s scanners have already
            produced. They never detect vulnerabilities, and they cannot change a
            score, a grade, or a finding. If a provider is unavailable, every
            security result stays exactly as it is.
          </p>
        </PanelBody>
      </Panel>

      <div className="space-y-4">
        {PROVIDERS.map((provider) => (
          <ProviderCard
            key={provider}
            provider={provider}
            credential={credentials.find((c) => c.provider === provider) ?? null}
            models={models.filter((m) => m.provider === provider)}
            onChanged={() => setReloadToken((n) => n + 1)}
          />
        ))}
      </div>
    </div>
  );
}

function ProviderCard({
  provider,
  credential,
  models,
  onChanged,
}: {
  provider: ProviderKey;
  credential: ProviderCredential | null;
  models: ProviderModel[];
  onChanged: () => void;
}) {
  const [apiKey, setApiKey] = useState("");
  const [modelId, setModelId] = useState(credential?.modelId ?? "");
  const [priority, setPriority] = useState(credential?.priority ?? 1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      if (apiKey.trim()) {
        await saveProvider({
          provider,
          apiKey: apiKey.trim(),
          modelId: modelId || null,
          priority,
        });
        // Cleared immediately. The key never lives in this component's state
        // for longer than the request that carried it.
        setApiKey("");
      } else if (credential) {
        await updateProvider(provider, { modelId: modelId || null, priority });
      }
      setSaved(true);
      onChanged();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await deleteProvider(provider);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>{PROVIDER_LABELS[provider]}</PanelTitle>
        <a
          href={PROVIDER_CONSOLES[provider]}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:underline"
        >
          Get an API key
          <ExternalLink className="size-3" aria-hidden="true" />
        </a>
      </PanelHeader>
      <PanelBody className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1.5 text-sm">
            <span className="font-medium">API key</span>
            <Input
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={
                credential?.keyPresent
                  ? `Stored — ends ${credential.keyHint}. Paste a new key to rotate.`
                  : "Paste your API key"
              }
              autoComplete="off"
            />
            <span className="block text-xs text-muted-foreground">
              Encrypted before storage. It is never sent back to your browser.
            </span>
          </label>

          <label className="space-y-1.5 text-sm">
            <span className="font-medium">Model</span>
            <Select value={modelId} onChange={(event) => setModelId(event.target.value)}>
              <option value="">Choose a model</option>
              {models.map((model) => (
                <option key={model.modelId} value={model.modelId}>
                  {model.displayName}
                  {model.contextWindow ? ` (${compact(model.contextWindow)} ctx)` : ""}
                </option>
              ))}
            </Select>
            {models.length === 0 ? (
              <span className="block text-xs text-muted-foreground">
                No models synced for this provider yet. An administrator needs to
                configure its catalogue credential.
              </span>
            ) : null}
          </label>
        </div>

        <label className="space-y-1.5 text-sm">
          <span className="font-medium">Order</span>
          <Select
            value={String(priority)}
            onChange={(event) => setPriority(Number(event.target.value))}
            className="max-w-xs"
          >
            <option value="1">Primary</option>
            <option value="2">Fallback (2nd)</option>
            <option value="3">Fallback (3rd)</option>
          </Select>
          <span className="block text-xs text-muted-foreground">
            Providers are tried in this order. Every explanation records which one
            answered, because switching vendor has billing and privacy
            consequences.
          </span>
        </label>

        {error ? <p className="text-sm text-severity-critical">{error}</p> : null}
        {saved ? <p className="text-sm text-severity-low">Saved.</p> : null}

        <div className="flex items-center gap-2">
          <Button onClick={() => void save()} disabled={busy || (!apiKey.trim() && !credential)}>
            {busy ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : null}
            {credential?.keyPresent ? "Save changes" : "Add provider"}
          </Button>
          {credential?.keyPresent ? (
            <Button variant="ghost" onClick={() => void remove()} disabled={busy}>
              <Trash2 className="size-4" aria-hidden="true" />
              Remove
            </Button>
          ) : null}
        </div>
      </PanelBody>
    </Panel>
  );
}

function compact(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}m`;
  if (value >= 1000) return `${Math.round(value / 1000)}k`;
  return String(value);
}
