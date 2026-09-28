"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ExternalLink, Loader2, Plus, RefreshCw, Trash2, X } from "lucide-react";

import { marketplaceAdminApi } from "@/entities/admin";
import {
  GradeBadge,
  ITEM_TYPE_LABELS,
  ITEM_TYPES,
  ItemContentSections,
  RelatedSection,
  ScanStatePill,
  TypeBadge,
  UseSection,
  toListingDetail,
  type ItemContent,
  type ItemType,
  type ListingDetail,
} from "@/entities/marketplace";
import { ApiError } from "@/shared/api";
import { Button, buttonVariants } from "@/shared/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";
import { Input } from "@/shared/ui/input";
import { Switch } from "@/shared/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import { EmptyState, PageHeader, Panel, PanelBody, PanelHeader, PanelTitle, Select } from "@/shared/ui";

import { Field, ListField, LongTextField, TextField } from "./editor-fields";

/**
 * Admin → Registry → one item: create it, edit it, move it through its
 * lifecycle, scan it, link it, preview it.
 *
 * Only the fields that changed are sent. Re-sending an untouched install
 * recipe would re-validate data written by the registry sync against the
 * stricter admin schema, and would open a new scan version for an MCP server
 * whose source had not moved.
 *
 * Publishing is refused by the server with every reason at once; the editor
 * shows them as the server gives them rather than guessing ahead of it, so
 * there is one definition of "ready to publish".
 */

type Raw = Record<string, unknown>;

interface Form {
  item_type: ItemType;
  title: string;
  description: string;
  author: string;
  publisher: string;
  repository_url: string;
  repository_ref: string;
  homepage_url: string;
  latest_version: string;
  license: string;
  categories: string[];
  tags: string[];
  technologies: string[];
  capabilities: string[];
  use_cases: string[];
  featured: boolean;
  visibility: string;
  content: ItemContent;
  installation: string;
}

function formFrom(raw: Raw): Form {
  const text = (key: string) => (raw[key] as string | null) ?? "";
  const list = (key: string) => (raw[key] as string[] | null) ?? [];
  return {
    item_type: ((raw.item_type as ItemType) ?? "mcp_server"),
    title: text("title"),
    description: text("description"),
    author: text("author"),
    publisher: text("publisher"),
    repository_url: text("repository_url"),
    repository_ref: text("repository_ref"),
    homepage_url: text("homepage_url"),
    latest_version: text("latest_version"),
    license: text("license"),
    categories: list("categories"),
    tags: list("tags"),
    technologies: list("technologies"),
    capabilities: list("capabilities"),
    use_cases: list("use_cases"),
    featured: Boolean(raw.featured),
    visibility: text("visibility") || "public",
    content: (raw.content as ItemContent) ?? {},
    installation: JSON.stringify(raw.installation ?? {}, null, 2),
  };
}

export function AdminItemEditorPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <AdminItemEditor itemId={id} />;
}

export function AdminItemCreatePage() {
  return <AdminItemEditor />;
}

function AdminItemEditor({ itemId }: { itemId?: string }) {
  if (!itemId) return <CreateItem />;
  return <EditItem itemId={itemId} />;
}

// --------------------------------------------------------------------------
// Create

function CreateItem() {
  const router = useRouter();
  const [itemType, setItemType] = useState<ItemType>("mcp_server");
  const [sourceUrl, setSourceUrl] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const created = await marketplaceAdminApi.create({
        item_type: itemType,
        source_url: sourceUrl.trim() || null,
        title: title.trim() || null,
        description: description.trim() || null,
      });
      router.push(`/admin/marketplace/${String(created.id)}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The item could not be created.");
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <BackLink />
      <PageHeader
        pretitle="Registry"
        title="New item"
        description="Every item starts as a draft. Nothing is public until you publish it."
      />
      <Panel>
        <PanelBody className="max-w-2xl space-y-5 py-6">
          <Field label="Type">
            {(id) => (
              <Select id={id} value={itemType} onChange={(event) => setItemType(event.target.value as ItemType)}>
                {ITEM_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {ITEM_TYPE_LABELS[type].one}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <TextField
            label="Source URL (optional)"
            hint="A GitHub repository or, for an MCP server, its hosted endpoint. Aevrin reads the name, description, licence and README from it, through the same checks a suggestion goes through."
            value={sourceUrl}
            onChange={setSourceUrl}
            placeholder="https://github.com/owner/repo"
            type="url"
          />
          <TextField
            label="Title"
            hint={sourceUrl ? "Optional: overrides the name read from the source." : "Required without a source URL."}
            value={title}
            onChange={setTitle}
            maxLength={120}
          />
          <LongTextField label="Description" value={description} onChange={setDescription} rows={3} />
          {error ? (
            <p className="text-sm text-severity-critical" role="alert">
              {error}
            </p>
          ) : null}
          <Button onClick={() => void create()} disabled={busy || (!sourceUrl.trim() && !title.trim())}>
            {busy ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Plus className="size-4" aria-hidden="true" />}
            Create draft
          </Button>
        </PanelBody>
      </Panel>
    </div>
  );
}

// --------------------------------------------------------------------------
// Edit

function EditItem({ itemId }: { itemId: string }) {
  const router = useRouter();
  const [raw, setRaw] = useState<Raw | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [version, setVersion] = useState(0);

  const load = useCallback(async () => {
    try {
      return await marketplaceAdminApi.get(itemId);
    } catch (error) {
      return error instanceof ApiError ? error : new ApiError(0, "That item could not be loaded.");
    }
  }, [itemId]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const result = await load();
      if (cancelled) return;
      if (result instanceof ApiError) {
        setLoadError(result.message);
        return;
      }
      setRaw(result);
      setForm(formFrom(result));
    })();
    return () => {
      cancelled = true;
    };
  }, [load, version]);

  const original = useMemo(() => (raw ? formFrom(raw) : null), [raw]);
  const preview: ListingDetail | null = useMemo(() => (raw ? toListingDetail(raw) : null), [raw]);

  if (loadError) {
    return (
      <div className="space-y-6">
        <BackLink />
        <EmptyState title="Item not found" body={loadError} />
      </div>
    );
  }
  if (!raw || !form || !original || !preview) {
    return (
      <div className="space-y-6">
        <BackLink />
        <PageHeader pretitle="Registry" title="Item" />
        <div className="flex items-center justify-center gap-2 py-24 text-muted-foreground" aria-busy>
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          <span className="text-sm">Loading…</span>
        </div>
      </div>
    );
  }

  const status = String(raw.status);
  const slug = String(raw.slug);
  const isServer = form.item_type === "mcp_server";
  const issues = (raw.validation_issues as string[]) ?? [];
  const set = <K extends keyof Form>(key: K, value: Form[K]) => setForm({ ...form, [key]: value });
  const setContent = <K extends keyof ItemContent>(key: K, value: ItemContent[K]) =>
    setForm({ ...form, content: { ...form.content, [key]: value } });

  async function act(key: string, fn: () => Promise<unknown>, done: string) {
    setBusy(key);
    setMessage(null);
    try {
      await fn();
      setMessage({ tone: "ok", text: done });
      setVersion((n) => n + 1);
    } catch (error) {
      setMessage({ tone: "error", text: error instanceof ApiError ? error.message : "That did not work." });
    } finally {
      setBusy(null);
    }
  }

  function changes(): Record<string, unknown> | string {
    const patch: Record<string, unknown> = {};
    for (const key of Object.keys(form!) as (keyof Form)[]) {
      if (key === "installation") continue;
      if (JSON.stringify(form![key]) !== JSON.stringify(original![key])) {
        const value = form![key];
        // An emptied text field clears the column rather than storing "".
        patch[key] = typeof value === "string" && value.trim() === "" && key !== "description" ? null : value;
      }
    }
    if (form!.installation !== original!.installation) {
      try {
        patch.installation = JSON.parse(form!.installation || "{}");
      } catch {
        return "The install recipe is not valid JSON.";
      }
    }
    return patch;
  }

  const save = () => {
    const patch = changes();
    if (typeof patch === "string") {
      setMessage({ tone: "error", text: patch });
      return;
    }
    if (!Object.keys(patch).length) {
      setMessage({ tone: "ok", text: "Nothing has changed." });
      return;
    }
    void act("save", () => marketplaceAdminApi.patch(itemId, patch), "Saved.");
  };

  const security = preview.security;

  return (
    <div className="space-y-6">
      <BackLink />
      <PageHeader
        pretitle="Registry"
        title={form.title || "Untitled"}
        description={`/${slug}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <TypeBadge type={form.item_type} />
            <span className="rounded-md border border-border px-2 py-0.5 text-xs font-medium">{status}</span>
            {status === "published" ? (
              <Link
                href={`/marketplace/${slug}`}
                className={buttonVariants({ size: "sm", variant: "ghost" })}
                target="_blank"
                rel="noopener"
              >
                View public page
                <ExternalLink className="size-3.5" aria-hidden="true" />
              </Link>
            ) : null}
          </div>
        }
      />

      {/* The lifecycle, in one bar. Every action writes the audit log. */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card p-3">
        <Button size="sm" onClick={save} disabled={busy !== null}>
          {busy === "save" ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : null}
          Save changes
        </Button>
        {status !== "published" && status !== "archived" ? (
          <Button
            size="sm"
            variant="outline"
            disabled={busy !== null}
            onClick={() => void act("publish", () => marketplaceAdminApi.setStatus(itemId, "published"), "Published.")}
          >
            Publish
          </Button>
        ) : null}
        {status === "published" ? (
          <Button
            size="sm"
            variant="outline"
            disabled={busy !== null}
            onClick={() =>
              void act("draft", () => marketplaceAdminApi.setStatus(itemId, "draft", "unpublished"), "Unpublished.")
            }
          >
            Unpublish
          </Button>
        ) : null}
        {status === "archived" ? (
          <Button
            size="sm"
            variant="outline"
            disabled={busy !== null}
            onClick={() => void act("restore", () => marketplaceAdminApi.setStatus(itemId, "draft", "restored"), "Restored to draft.")}
          >
            Restore
          </Button>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            disabled={busy !== null}
            onClick={() => void act("archive", () => marketplaceAdminApi.setStatus(itemId, "archived", "archived"), "Archived.")}
          >
            Archive
          </Button>
        )}
        {form.repository_url && original.repository_url === form.repository_url ? (
          <Button
            size="sm"
            variant="ghost"
            disabled={busy !== null}
            onClick={() => void act("refresh", () => marketplaceAdminApi.refreshMetadata(itemId), "Repository signals and README refreshed.")}
          >
            <RefreshCw className="size-3.5" aria-hidden="true" />
            Refresh from repository
          </Button>
        ) : null}
        <Button
          size="sm"
          variant="ghost"
          className="ms-auto text-severity-critical"
          disabled={busy !== null}
          onClick={() => setDeleteOpen(true)}
        >
          <Trash2 className="size-3.5" aria-hidden="true" />
          Delete
        </Button>
      </div>

      {message ? (
        <p
          role={message.tone === "error" ? "alert" : "status"}
          className={`rounded-lg border px-4 py-3 text-sm ${
            message.tone === "error"
              ? "border-severity-critical/30 bg-severity-critical/5 text-severity-critical"
              : "border-border bg-muted/40"
          }`}
        >
          {message.text}
        </p>
      ) : null}

      {issues.length && status !== "published" ? (
        <Panel>
          <PanelHeader>
            <PanelTitle>Before this can be published</PanelTitle>
          </PanelHeader>
          <PanelBody>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {issues.map((issue) => (
                <li key={issue}>{issue}</li>
              ))}
            </ul>
          </PanelBody>
        </Panel>
      ) : null}

      {/* Remounted after every save, so the uncontrolled list fields show
          what the server stored rather than what was typed before it. */}
      <Tabs key={String(raw.updated_at)} defaultValue="details">
        <TabsList className="flex-wrap">
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="content">Content</TabsTrigger>
          {isServer ? <TabsTrigger value="install">Install</TabsTrigger> : null}
          {isServer ? <TabsTrigger value="security">Security</TabsTrigger> : null}
          <TabsTrigger value="links">Related</TabsTrigger>
          <TabsTrigger value="preview">Preview</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="details">
          <Panel>
            <PanelBody className="grid gap-5 py-6 md:grid-cols-2">
              <Field label="Type">
                {(id) => (
                  <Select id={id} value={form.item_type} onChange={(event) => set("item_type", event.target.value as ItemType)}>
                    {ITEM_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {ITEM_TYPE_LABELS[type].one}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
              <TextField label="Title" value={form.title} onChange={(v) => set("title", v)} maxLength={120} />
              <div className="md:col-span-2">
                <LongTextField
                  label="Description"
                  hint="What search matches, and what an agent reads to decide whether this is relevant."
                  value={form.description}
                  onChange={(v) => set("description", v)}
                  rows={3}
                />
              </div>
              <TextField label="Author" value={form.author} onChange={(v) => set("author", v)} />
              <TextField label="Organisation" value={form.publisher} onChange={(v) => set("publisher", v)} />
              <TextField label="Repository URL" value={form.repository_url} onChange={(v) => set("repository_url", v)} type="url" />
              <TextField
                label="Branch, tag or commit"
                hint="Shown in the copyable clone command."
                value={form.repository_ref}
                onChange={(v) => set("repository_ref", v)}
              />
              <TextField label="Homepage URL" value={form.homepage_url} onChange={(v) => set("homepage_url", v)} type="url" />
              <TextField
                label="Version"
                hint={isServer ? "Changing it opens a new, unscanned version: the current grade will show as outdated." : undefined}
                value={form.latest_version}
                onChange={(v) => set("latest_version", v)}
              />
              <TextField label="Licence" value={form.license} onChange={(v) => set("license", v)} />
              <Field label="Visibility">
                {(id) => (
                  <Select id={id} value={form.visibility} onChange={(event) => set("visibility", event.target.value)}>
                    <option value="public">Public</option>
                    <option value="unlisted">Unlisted (reachable by link)</option>
                    <option value="private">Private (organisation only)</option>
                  </Select>
                )}
              </Field>
              <ListField label="Categories" hint="Category slugs, comma-separated. They must exist." values={form.categories} onChange={(v) => set("categories", v)} />
              <ListField label="Tags" values={form.tags} onChange={(v) => set("tags", v)} />
              <ListField label="Technologies" hint="e.g. node.js, aws, react" values={form.technologies} onChange={(v) => set("technologies", v)} />
              <ListField label="Capabilities" hint="What it can do, e.g. deploy, lint, search-docs" values={form.capabilities} onChange={(v) => set("capabilities", v)} />
              <div className="md:col-span-2">
                <ListField
                  label="Use cases"
                  hint="The goals an agent searches with, e.g. deploy a node backend"
                  values={form.use_cases}
                  onChange={(v) => set("use_cases", v)}
                />
              </div>
              <label className="flex items-center gap-3 text-sm font-medium">
                <Switch checked={form.featured} onCheckedChange={(checked) => set("featured", checked)} />
                Featured
              </label>
            </PanelBody>
          </Panel>
        </TabsContent>

        <TabsContent value="content">
          <Panel>
            <PanelBody className="space-y-5 py-6">
              {form.item_type === "prompt" || form.content.prompt ? (
                <LongTextField label="Prompt" value={form.content.prompt ?? ""} onChange={(v) => setContent("prompt", v)} rows={10} mono />
              ) : null}
              {form.item_type === "skill" || form.item_type === "agent" || form.content.instructions ? (
                <LongTextField
                  label="Instructions"
                  hint="What the agent should do with this item. Returned to agents as written."
                  value={form.content.instructions ?? ""}
                  onChange={(v) => setContent("instructions", v)}
                  rows={10}
                  mono
                />
              ) : null}
              <LongTextField label="Usage" value={form.content.usage ?? ""} onChange={(v) => setContent("usage", v)} rows={5} />
              <LongTextField label="Documentation" value={form.content.documentation ?? ""} onChange={(v) => setContent("documentation", v)} rows={10} />
              <div className="grid gap-5 md:grid-cols-2">
                <ListField label="Inputs" separator="line" values={form.content.inputs ?? []} onChange={(v) => setContent("inputs", v)} />
                <ListField label="Outputs" separator="line" values={form.content.outputs ?? []} onChange={(v) => setContent("outputs", v)} />
                <ListField label="Dependencies" separator="line" values={form.content.dependencies ?? []} onChange={(v) => setContent("dependencies", v)} />
                <ListField label="Works with" separator="line" values={form.content.compatibility ?? []} onChange={(v) => setContent("compatibility", v)} />
              </div>
              <Examples
                examples={form.content.examples ?? []}
                onChange={(examples) => setContent("examples", examples)}
              />
            </PanelBody>
          </Panel>
        </TabsContent>

        {isServer ? (
          <TabsContent value="install">
            <Panel>
              <PanelBody className="space-y-3 py-6">
                <LongTextField
                  label="Install recipe (JSON)"
                  hint='{"packages": [{"registry_type": "npm", "identifier": "@scope/server", "version": "1.2.0", "environment": [{"name": "API_KEY", "secret": true}]}], "remotes": [{"type": "streamable-http", "url": "https://..."}]}. Secret values are never stored: name the variable and mark it secret. Changing this opens a new, unscanned version.'
                  value={form.installation}
                  onChange={(v) => set("installation", v)}
                  rows={14}
                  mono
                />
              </PanelBody>
            </Panel>
          </TabsContent>
        ) : null}

        {isServer ? (
          <TabsContent value="security">
            <Panel>
              <PanelBody className="space-y-5 py-6">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <GradeBadge grade={security.grade} riskScore={security.risk_score} state={security.state} size="lg" />
                  <ScanStatePill security={security} />
                </div>
                <p className="text-sm text-muted-foreground">{security.label}</p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    disabled={busy !== null}
                    onClick={() =>
                      void act(
                        "scan",
                        () => marketplaceAdminApi.scan(itemId, false),
                        "Scan requested. The result appears here when it finishes; reload in a minute.",
                      )
                    }
                  >
                    Scan
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy !== null}
                    onClick={() =>
                      void act(
                        "rescan",
                        () => marketplaceAdminApi.scan(itemId, true),
                        "A fresh scan was started. Reload in a minute for the result.",
                      )
                    }
                  >
                    <RefreshCw className="size-3.5" aria-hidden="true" />
                    Force rescan
                  </Button>
                </div>
                {preview.gradeRationale?.drivers.length ? (
                  <div>
                    <p className="mb-2 text-sm font-medium">Findings behind the grade</p>
                    <ul className="divide-y divide-border rounded-md border border-border">
                      {preview.gradeRationale.drivers.map((driver) => (
                        <li key={driver.ruleId} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                          <span>
                            {driver.label}
                            <span className="ml-2 text-xs text-muted-foreground tabular-nums">
                              {driver.ruleId} · {driver.occurrences} {driver.occurrences === 1 ? "tool" : "tools"}
                            </span>
                          </span>
                          <span className="text-xs font-medium uppercase">{driver.severity}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                <div>
                  <p className="mb-2 text-sm font-medium">Versions</p>
                  <ul className="space-y-1 text-sm">
                    {preview.versions.map((v) => (
                      <li key={v.id} className="flex justify-between gap-3 rounded-md border border-border px-3 py-1.5">
                        <span className="font-mono text-xs">{v.version}</span>
                        <span className="text-xs text-muted-foreground">
                          {v.trustGrade ? `Grade ${v.trustGrade}` : v.scanId ? "scanned, not graded" : "not scanned"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              </PanelBody>
            </Panel>
          </TabsContent>
        ) : null}

        <TabsContent value="links">
          <LinksEditor
            itemId={itemId}
            current={(raw.related as Raw[]) ?? []}
            onSaved={() => {
              setMessage({ tone: "ok", text: "Related items saved." });
              setVersion((n) => n + 1);
            }}
          />
        </TabsContent>

        <TabsContent value="preview">
          <div className="space-y-6">
            <p className="text-sm text-muted-foreground">
              What a visitor sees for the saved version of this item. Unsaved edits are not shown.
            </p>
            <UseSection listing={preview} />
            <ItemContentSections listing={preview} />
            <RelatedSection listing={preview} />
          </div>
        </TabsContent>

        <TabsContent value="history">
          <Panel>
            <PanelBody className="space-y-2 py-6">
              {preview.events.length === 0 ? (
                <p className="text-sm text-muted-foreground">No events yet.</p>
              ) : (
                preview.events.map((event) => (
                  <div key={event.id} className="text-sm">
                    <span className="font-medium">{event.eventType.replace(/_/g, " ")}</span>
                    {event.oldValue || event.newValue ? (
                      <span className="text-muted-foreground">
                        {": "}
                        {event.oldValue ?? ""} → {event.newValue ?? ""}
                      </span>
                    ) : null}
                    <span className="ml-2 text-xs text-muted-foreground">{new Date(event.createdAt).toLocaleString()}</span>
                    {event.reason ? <p className="text-xs text-muted-foreground">{event.reason}</p> : null}
                  </div>
                ))
              )}
            </PanelBody>
          </Panel>
        </TabsContent>
      </Tabs>

      <DeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        slug={slug}
        onDelete={async (confirm) => {
          await marketplaceAdminApi.remove(itemId, confirm);
          router.push("/admin/marketplace");
        }}
      />
    </div>
  );
}

// --------------------------------------------------------------------------
// Pieces

function BackLink() {
  return (
    <Link href="/admin/marketplace" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" aria-hidden="true" />
      Registry
    </Link>
  );
}

function Examples({
  examples,
  onChange,
}: {
  examples: { title?: string; body: string }[];
  onChange: (examples: { title?: string; body: string }[]) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">Examples</p>
        <Button size="sm" variant="outline" type="button" onClick={() => onChange([...examples, { title: "", body: "" }])}>
          <Plus className="size-3.5" aria-hidden="true" />
          Add example
        </Button>
      </div>
      {examples.map((example, index) => (
        <div key={index} className="space-y-2 rounded-md border border-border p-3">
          <div className="flex items-center gap-2">
            <Input
              aria-label={`Example ${index + 1} title`}
              placeholder="Title"
              value={example.title ?? ""}
              onChange={(event) =>
                onChange(examples.map((e, i) => (i === index ? { ...e, title: event.target.value } : e)))
              }
            />
            <Button
              size="sm"
              variant="ghost"
              type="button"
              aria-label={`Remove example ${index + 1}`}
              onClick={() => onChange(examples.filter((_, i) => i !== index))}
            >
              <X className="size-4" aria-hidden="true" />
            </Button>
          </div>
          <textarea
            aria-label={`Example ${index + 1} body`}
            className="min-h-24 w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-xs"
            value={example.body}
            onChange={(event) =>
              onChange(examples.map((e, i) => (i === index ? { ...e, body: event.target.value } : e)))
            }
          />
        </div>
      ))}
    </div>
  );
}

function LinksEditor({ itemId, current, onSaved }: { itemId: string; current: Raw[]; onSaved: () => void }) {
  const [links, setLinks] = useState(
    current.map((r) => ({
      related_id: String(r.id),
      relation: (r.relation === "uses" ? "uses" : "related") as "uses" | "related",
      title: String(r.title ?? r.slug),
      status: String(r.status ?? ""),
    })),
  );
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Raw[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search() {
    const rows = await marketplaceAdminApi.list({ q: query.trim() || undefined, limit: 10 }).catch(() => []);
    setResults(rows.filter((r) => String(r.id) !== itemId && !links.some((l) => l.related_id === String(r.id))));
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await marketplaceAdminApi.setLinks(itemId, links.map(({ related_id, relation }) => ({ related_id, relation })));
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The links could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel>
      <PanelBody className="space-y-4 py-6">
        <p className="text-sm text-muted-foreground">
          The public page shows only related items that are published. Link to drafts freely; they
          appear once published.
        </p>
        <ul className="space-y-2">
          {links.map((link, index) => (
            <li key={link.related_id} className="flex flex-wrap items-center gap-2 rounded-md border border-border px-3 py-2 text-sm">
              <span className="min-w-0 flex-1 truncate">
                {link.title}
                {link.status && link.status !== "published" ? (
                  <span className="ml-2 text-xs text-muted-foreground">({link.status})</span>
                ) : null}
              </span>
              <Select
                aria-label={`Relation to ${link.title}`}
                value={link.relation}
                onChange={(event) =>
                  setLinks(links.map((l, i) => (i === index ? { ...l, relation: event.target.value as "uses" | "related" } : l)))
                }
              >
                <option value="related">Related</option>
                <option value="uses">Uses</option>
              </Select>
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Remove link to ${link.title}`}
                onClick={() => setLinks(links.filter((_, i) => i !== index))}
              >
                <X className="size-4" aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void search();
          }}
        >
          <Input
            aria-label="Find items to link"
            placeholder="Find an item by title"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="min-w-[220px] flex-1"
          />
          <Button type="submit" variant="outline" size="sm">
            Find
          </Button>
        </form>
        {results.length ? (
          <ul className="space-y-1">
            {results.map((r) => (
              <li key={String(r.id)}>
                <button
                  type="button"
                  className="w-full rounded-md px-3 py-1.5 text-left text-sm hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                  onClick={() => {
                    setLinks([...links, { related_id: String(r.id), relation: "related", title: String(r.title), status: String(r.status) }]);
                    setResults(results.filter((x) => x.id !== r.id));
                  }}
                >
                  <Plus className="mr-1.5 inline size-3.5" aria-hidden="true" />
                  {String(r.title)}
                  <span className="ml-2 text-xs text-muted-foreground">{ITEM_TYPE_LABELS[(r.item_type as ItemType) ?? "mcp_server"]?.one}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        {error ? (
          <p className="text-sm text-severity-critical" role="alert">
            {error}
          </p>
        ) : null}
        <Button size="sm" onClick={() => void save()} disabled={busy}>
          {busy ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : null}
          Save related items
        </Button>
      </PanelBody>
    </Panel>
  );
}

function DeleteDialog({
  open,
  onOpenChange,
  slug,
  onDelete,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  slug: string;
  onDelete: (confirmSlug: string) => Promise<void>;
}) {
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) {
          setConfirm("");
          setError(null);
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete this item</DialogTitle>
          <DialogDescription>
            This removes the registry entry, its versions, links and timeline. It does not touch the
            repository, the package, or any scan. Archiving hides an item and keeps it; deleting cannot
            be undone. Type <span className="font-mono font-medium">{slug}</span> to confirm.
          </DialogDescription>
        </DialogHeader>
        <Input
          aria-label="Type the slug to confirm"
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          autoComplete="off"
        />
        {error ? (
          <p className="text-sm text-severity-critical" role="alert">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={confirm !== slug || busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                await onDelete(confirm);
              } catch (err) {
                setError(err instanceof ApiError ? err.message : "The item could not be deleted.");
                setBusy(false);
              }
            }}
          >
            {busy ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : null}
            Delete permanently
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
