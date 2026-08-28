"use client";

import { useEffect, useState } from "react";
import { Check, ExternalLink, Loader2, Trash2 } from "lucide-react";

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
import { BrandIcon, type BrandName } from "@/shared/ui/brand-icon";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";
import { PageHeader, Panel, PanelBody, Select } from "@/shared/ui";

/**
 * Settings → AI providers.
 *
 * A roster, not four open forms. Every provider is one row saying what it is
 * and whether it is connected; configuration happens in a dialog, because a
 * key and a model are a decision someone makes once rather than fields they
 * scan past on the way to something else.
 *
 * The dialog is two steps, in the order the data actually becomes available:
 * a key, then a model. That is not a UX preference. Aevrin has no catalogue
 * credential of its own here, so a provider's model list is only knowable
 * *after* a key exists to ask with -- saving one triggers that refresh (see
 * `DECISIONS.md` ADR-012). Offering the model dropdown first, as this page
 * used to, meant offering an empty one.
 *
 * The key input is write-only. Once saved the field clears and what remains on
 * screen is "ends 4f2a". There is no view, no reveal, and no request that
 * could fetch it back: the API has no endpoint that returns a key, so this
 * page could not display one even if it tried.
 *
 * Nothing here claims any provider is free. Free tiers change, and a security
 * tool that told someone an API cost nothing when it had started charging
 * would have created a real problem for no benefit.
 */

const PROVIDERS: ProviderKey[] = ["groq", "gemini", "anthropic", "openai"];

// Each provider's own mark, from `thesvg` via BrandIcon. Named per provider
// rather than derived, so a provider without a real mark is a compile error
// here instead of a blank tile in production.
const PROVIDER_BRANDS: Record<ProviderKey, BrandName> = {
  groq: "groq",
  gemini: "gemini",
  anthropic: "anthropic",
  openai: "openai",
};

export function AiProvidersPage() {
  const [credentials, setCredentials] = useState<ProviderCredential[]>([]);
  const [models, setModels] = useState<ProviderModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<ProviderKey | null>(null);

  // Bumped after a save, which re-runs the effect below. Refreshing through a
  // counter rather than a shared setter keeps every state update inside an
  // async continuation, where React wants it.
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

  const active = open
    ? {
        provider: open,
        credential: credentials.find((c) => c.provider === open) ?? null,
        models: models.filter((m) => m.provider === open),
      }
    : null;

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

      <Panel>
        <PanelBody className="p-0">
          <ul className="divide-y divide-border">
            {PROVIDERS.map((provider) => {
              const credential = credentials.find((c) => c.provider === provider) ?? null;
              const connected = Boolean(credential?.keyPresent);
              const model = models.find((m) => m.modelId === credential?.modelId);

              return (
                <li
                  key={provider}
                  className="flex items-center gap-4 px-4 py-3 sm:px-5 sm:py-4"
                >
                  <span className="grid size-10 shrink-0 place-items-center rounded-lg border border-border bg-muted/40">
                    <BrandIcon name={PROVIDER_BRANDS[provider]} className="size-5" />
                  </span>

                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{PROVIDER_LABELS[provider]}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {connected ? (
                        <>
                          Key ends {credential?.keyHint}
                          {credential?.modelId
                            ? ` · ${model?.displayName ?? credential.modelId}`
                            : " · no model chosen"}
                        </>
                      ) : (
                        "Not connected"
                      )}
                    </p>
                  </div>

                  {connected ? (
                    <span
                      className="hidden shrink-0 items-center gap-1.5 rounded-full border border-brand/25 bg-brand/10 px-2 py-0.5 text-[11px] font-medium text-brand-text sm:inline-flex"
                    >
                      <Check className="size-3" aria-hidden="true" />
                      Connected
                    </span>
                  ) : null}

                  <Button
                    variant={connected ? "outline" : "default"}
                    size="sm"
                    className="shrink-0"
                    onClick={() => setOpen(provider)}
                  >
                    {connected ? "Manage" : "Connect"}
                    <span className="sr-only"> {PROVIDER_LABELS[provider]}</span>
                  </Button>
                </li>
              );
            })}
          </ul>
        </PanelBody>
      </Panel>

      {active ? (
        <ProviderDialog
          key={active.provider}
          provider={active.provider}
          credential={active.credential}
          models={active.models}
          open
          onOpenChange={(next) => setOpen(next ? active.provider : null)}
          onChanged={() => setReloadToken((n) => n + 1)}
        />
      ) : null}
    </div>
  );
}

function ProviderDialog({
  provider,
  credential,
  models,
  open,
  onOpenChange,
  onChanged,
}: {
  provider: ProviderKey;
  credential: ProviderCredential | null;
  models: ProviderModel[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChanged: () => void;
}) {
  const connected = Boolean(credential?.keyPresent);
  // A connected provider opens on the model step: its key is already stored,
  // and the only reason to come back is to change the model or rotate.
  const [step, setStep] = useState<"key" | "model">(connected ? "model" : "key");
  const [apiKey, setApiKey] = useState("");
  const [modelId, setModelId] = useState(credential?.modelId ?? "");
  const [priority, setPriority] = useState(credential?.priority ?? 1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function submitKey() {
    if (!apiKey.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await saveProvider({
        provider,
        apiKey: apiKey.trim(),
        modelId: modelId || null,
        priority,
      });
      // Cleared immediately. The key never lives in this component's state for
      // longer than the request that carried it.
      setApiKey("");
      // Saving refreshes this provider's model catalogue server-side, so the
      // parent reload is what makes the next step have anything to offer.
      onChanged();
      setStep("model");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not save the key.");
    } finally {
      setBusy(false);
    }
  }

  async function submitModel() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await updateProvider(provider, { modelId: modelId || null, priority });
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
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2.5">
            <BrandIcon name={PROVIDER_BRANDS[provider]} className="size-5" />
            {PROVIDER_LABELS[provider]}
          </DialogTitle>
          <DialogDescription>
            {step === "key"
              ? "Paste an API key. It is encrypted before storage and never sent back to your browser."
              : "Choose which model answers, and where this provider sits in the order."}
          </DialogDescription>
        </DialogHeader>

        {step === "key" ? (
          <div className="space-y-4">
            <label className="block space-y-1.5 text-sm">
              <span className="font-medium">API key</span>
              <Input
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={
                  connected
                    ? `Stored, ends ${credential?.keyHint}. Paste a new key to rotate.`
                    : "Paste your API key"
                }
                autoComplete="off"
                autoFocus
              />
            </label>

            <a
              href={PROVIDER_CONSOLES[provider]}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:underline"
            >
              Get an API key from {PROVIDER_LABELS[provider]}
              <ExternalLink className="size-3" aria-hidden="true" />
            </a>

            {error ? <p className="text-sm text-severity-critical">{error}</p> : null}
          </div>
        ) : (
          <div className="space-y-4">
            <label className="block space-y-1.5 text-sm">
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
                  No models have been read from this provider yet. Rotating the key
                  refreshes the list; if it stays empty, the key may not have access
                  to the model listing.
                </span>
              ) : null}
            </label>

            <label className="block space-y-1.5 text-sm">
              <span className="font-medium">Order</span>
              <Select
                value={String(priority)}
                onChange={(event) => setPriority(Number(event.target.value))}
              >
                <option value="1">Primary</option>
                <option value="2">Fallback (2nd)</option>
                <option value="3">Fallback (3rd)</option>
              </Select>
              <span className="block text-xs text-muted-foreground">
                Providers are tried in this order. Every explanation records which
                one answered, because switching vendor has billing and privacy
                consequences.
              </span>
            </label>

            <button
              type="button"
              onClick={() => {
                setStep("key");
                setSaved(false);
                setError(null);
              }}
              className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              Replace the API key
            </button>

            {error ? <p className="text-sm text-severity-critical">{error}</p> : null}
            {saved ? <p className="text-sm text-brand-text">Saved.</p> : null}
          </div>
        )}

        <DialogFooter className="sm:justify-between">
          {connected ? (
            <Button variant="ghost" onClick={() => void remove()} disabled={busy}>
              <Trash2 className="size-4" aria-hidden="true" />
              Disconnect
            </Button>
          ) : (
            <span />
          )}

          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              {step === "model" ? "Done" : "Cancel"}
            </Button>
            <Button
              onClick={() => void (step === "key" ? submitKey() : submitModel())}
              disabled={busy || (step === "key" && !apiKey.trim())}
            >
              {busy ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : null}
              {step === "key" ? "Continue" : "Save"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function compact(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}m`;
  if (value >= 1000) return `${Math.round(value / 1000)}k`;
  return String(value);
}
