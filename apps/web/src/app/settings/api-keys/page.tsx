"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, KeyRound, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { ApiKey } from "@/lib/types";
import { CopyButton } from "@/components/copy-button";
import { PageHeader, SectionCard } from "@/components/product-ui";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatDate, formatDateTime } from "@/lib/presentation";
import { AGENT_HOOK_PROMPT, AGENT_INSTALL_PROMPT, API_KEY_ENV_COMMANDS } from "@/lib/onboarding";

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [name, setName] = useState("CLI key");
  const [creating, setCreating] = useState(false);
  const [justCreated, setJustCreated] = useState<string | null>(null);
  const [pendingRevoke, setPendingRevoke] = useState<ApiKey | null>(null);

  function refresh() {
    api
      .listApiKeys()
      .then(setKeys)
      .catch((err) => {
        setKeys([]);
        toast.error(err instanceof ApiError ? err.message : "Could not load API keys.");
      });
  }

  useEffect(refresh, []);

  async function create() {
    if (!name.trim()) {
      toast.error("Name the key so you can identify it later.");
      return;
    }
    setCreating(true);
    try {
      const result = await api.createApiKey(name.trim());
      setJustCreated(result.plaintext_key);
      setName("CLI key");
      refresh();
      toast.success("API key created");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not create API key.");
    } finally {
      setCreating(false);
    }
  }

  async function revokeConfirmed() {
    if (!pendingRevoke) return;
    try {
      await api.revokeApiKey(pendingRevoke.id);
      toast.success(`Revoked ${pendingRevoke.name}`);
      setPendingRevoke(null);
      refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not revoke the API key.");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="API keys"
        description="Use API keys for CI and automation. Interactive device login remains the default developer path because it avoids long-lived secrets on local machines."
      />

      {justCreated ? (
        <Alert>
          <KeyRound className="size-4" />
          <AlertTitle>Copy this secret now</AlertTitle>
          <AlertDescription className="space-y-4">
            <p>This key is shown once only. It will not be available again after you leave this page.</p>
            <div className="rounded-2xl border border-border bg-background/80 p-4">
              <code className="block break-all font-mono text-sm">{justCreated}</code>
              <div className="mt-3 flex flex-wrap gap-3">
                <CopyButton value={justCreated} label="Copy secret" />
                <CopyButton value={`export AEVRIN_API_KEY="${justCreated}"`} label="Copy macOS/Linux export" />
                <CopyButton value={`$env:AEVRIN_API_KEY="${justCreated}"`} label="Copy PowerShell env" />
                <CopyButton value={`set AEVRIN_API_KEY=${justCreated}`} label="Copy CMD env" />
              </div>
            </div>
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_360px]">
        <SectionCard
          title="Create key"
          description="Keys currently support a name, creation time, last-used time when available, and revocation. Scope, expiry, and masked prefix are not yet enforced by the backend, so they are not simulated here."
        >
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="key-name">Key name</Label>
              <Input
                id="key-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="CI deploy key"
              />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={create} disabled={creating}>
                {creating ? "Creating…" : "Create API key"}
              </Button>
              <p className="text-sm text-muted-foreground">
                The full secret is revealed once and never rendered again after creation.
              </p>
            </div>
          </div>
        </SectionCard>

        <SectionCard
          title="Safe usage"
          description="Keep the secret in environment variables or a proper secret manager, not in source files, logs, screenshots, or checked-in CI configuration."
        >
          <div className="grid gap-4">
            {API_KEY_ENV_COMMANDS.map((item) => (
              <CodePanel
                key={item.id}
                title={item.label}
                value={item.value}
                action={<CopyButton value={item.value} label="Copy commands" />}
              />
            ))}
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="Agent-ready setup prompts"
        description="These prompts are for Claude Code or another agent when you want it to perform the install or hook setup on your behalf."
      >
        <div className="grid gap-4 xl:grid-cols-2">
          <PromptPanel
            title="Install prompt"
            value={AGENT_INSTALL_PROMPT}
            label="Copy install prompt"
          />
          <PromptPanel
            title="Hook prompt"
            value={AGENT_HOOK_PROMPT}
            label="Copy hook prompt"
          />
        </div>
      </SectionCard>

      <SectionCard
        title="Existing keys"
        description="Only real backend fields are shown below."
      >
        <div className="space-y-3">
          {keys === null ? (
            Array.from({ length: 3 }).map((_, index) => <Skeleton key={index} className="h-24 rounded-2xl" />)
          ) : keys.length === 0 ? (
            <Alert>
              <AlertTriangle className="size-4" />
              <AlertTitle>No API keys yet</AlertTitle>
              <AlertDescription>
                Create a key only if you need non-interactive automation such as CI or scheduled jobs.
              </AlertDescription>
            </Alert>
          ) : (
            keys.map((key) => (
              <div
                key={key.id}
                className="flex flex-col gap-4 rounded-2xl border border-border bg-background/80 p-4 lg:flex-row lg:items-center lg:justify-between"
              >
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-base font-medium text-foreground">{key.name}</span>
                    <span className="rounded-full border border-border px-2 py-1 text-xs text-muted-foreground">
                      {key.revoked_at ? "Revoked" : "Active"}
                    </span>
                  </div>
                  <div className="grid gap-1 text-sm text-muted-foreground sm:grid-cols-2">
                    <span>Created: {formatDate(key.created_at)}</span>
                    <span>Last used: {key.last_used_at ? formatDateTime(key.last_used_at) : "Not recorded yet"}</span>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {!key.revoked_at ? (
                    <Button variant="destructive" onClick={() => setPendingRevoke(key)}>
                      <Trash2 className="size-4" />
                      Revoke
                    </Button>
                  ) : null}
                </div>
              </div>
            ))
          )}
        </div>
      </SectionCard>

      <Dialog open={Boolean(pendingRevoke)} onOpenChange={(open) => (!open ? setPendingRevoke(null) : null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke API key</DialogTitle>
            <DialogDescription>
              {pendingRevoke
                ? `Revoke ${pendingRevoke.name}? Existing automation that depends on it will stop authenticating immediately.`
                : "Revoke this key?"}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPendingRevoke(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void revokeConfirmed()}>
              Revoke key
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CodePanel({
  title,
  value,
  action,
}: {
  title: string;
  value: string;
  action?: React.ReactNode;
}) {
  return (
    <Card className="bg-background/80">
      <CardContent className="space-y-3 pt-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm font-medium text-foreground">{title}</p>
          {action}
        </div>
        <pre className="overflow-x-auto rounded-2xl border border-border bg-background px-4 py-3 font-mono text-xs leading-6 text-foreground sm:text-sm">
          {value}
        </pre>
      </CardContent>
    </Card>
  );
}

function PromptPanel({
  title,
  value,
  label,
}: {
  title: string;
  value: string;
  label: string;
}) {
  return (
    <Card className="bg-background/80">
      <CardContent className="space-y-4 pt-5">
        <div className="space-y-2">
          <p className="text-base font-medium text-foreground">{title}</p>
          <p className="text-sm leading-6 text-muted-foreground">
            Paste this into an agent if you want the setup executed for you with the current product workflow.
          </p>
        </div>
        <pre className="overflow-x-auto rounded-2xl border border-border bg-background px-4 py-3 whitespace-pre-wrap font-mono text-xs leading-6 text-foreground sm:text-sm">
          {value}
        </pre>
        <CopyButton value={value} label={label} />
      </CardContent>
    </Card>
  );
}
