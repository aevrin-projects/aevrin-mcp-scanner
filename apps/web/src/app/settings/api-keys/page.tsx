"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { ApiKey } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { KeyRound } from "lucide-react";

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [name, setName] = useState("CLI key");
  const [creating, setCreating] = useState(false);
  const [justCreated, setJustCreated] = useState<string | null>(null);

  function refresh() {
    api
      .listApiKeys()
      .then(setKeys)
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Could not load API keys."));
  }

  useEffect(refresh, []);

  async function create() {
    setCreating(true);
    try {
      const result = await api.createApiKey(name || "CLI key");
      setJustCreated(result.plaintext_key);
      refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not create API key.");
    } finally {
      setCreating(false);
    }
  }

  async function revoke(id: number) {
    try {
      await api.revokeApiKey(id);
      toast.success("API key revoked");
      refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not revoke API key.");
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="text-2xl font-semibold tracking-tight">API keys</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Used by <code>aevrin scan --upload</code> and the Claude Code hook. Set{" "}
        <code>AEVRIN_API_KEY</code> in your environment.
      </p>

      {justCreated && (
        <Alert className="mt-6">
          <KeyRound className="size-4" />
          <AlertTitle>Copy this key now — it won&apos;t be shown again</AlertTitle>
          <AlertDescription>
            <code className="mt-1 block break-all rounded bg-muted px-2 py-1">{justCreated}</code>
          </AlertDescription>
        </Alert>
      )}

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base font-medium">Create a new key</CardTitle>
          <CardDescription>Give it a name so you can tell keys apart later.</CardDescription>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="CLI key" />
          <Button onClick={create} disabled={creating}>
            {creating ? "Creating…" : "Create key"}
          </Button>
        </CardContent>
      </Card>

      <div className="mt-8 flex flex-col gap-2">
        {keys === null && <Skeleton className="h-14 w-full" />}
        {keys?.length === 0 && <p className="text-sm text-muted-foreground">No API keys yet.</p>}
        {keys?.map((key) => (
          <div
            key={key.id}
            className="flex items-center justify-between rounded-lg border border-border px-4 py-3"
          >
            <div>
              <p className="text-sm font-medium">{key.name}</p>
              <p className="text-xs text-muted-foreground">
                Created {new Date(key.created_at).toLocaleDateString()}
                {key.last_used_at && ` · last used ${new Date(key.last_used_at).toLocaleDateString()}`}
              </p>
            </div>
            {key.revoked_at ? (
              <Badge variant="outline">Revoked</Badge>
            ) : (
              <Button variant="ghost" size="sm" onClick={() => revoke(key.id)}>
                Revoke
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
