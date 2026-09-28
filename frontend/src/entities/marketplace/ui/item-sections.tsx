"use client";

import Link from "next/link";

import { INSTALL_TARGET_LABELS, type InstallTarget, type ListingDetail } from "../model/types";
import { AevrinMcpSnippet } from "./aevrin-mcp-snippet";
import { TypeBadge } from "./type-badge";
import { CopyButton } from "@/shared/ui/copy-button";
import { Panel, PanelBody, PanelHeader, PanelTitle } from "@/shared/ui";

/**
 * The parts of an item page that depend on what the item is. Shared by the
 * public item page and the admin editor's preview, so what an administrator
 * previews is what a visitor sees.
 *
 * Every body here is rendered as text, never as HTML. A registry item's
 * content is written by an administrator, but a README is a stranger's, and
 * the rule is simplest - and safest - applied to both.
 *
 * Actions appear only where the item supports them: no clone command for an
 * item without a repository, no MCP config for anything that is not a server.
 */

export function ItemContentSections({ listing }: { listing: ListingDetail }) {
  const { content } = listing;
  const blocks: { title: string; body: string; copy?: boolean }[] = [];
  if (content.prompt) blocks.push({ title: "Prompt", body: content.prompt, copy: true });
  if (content.instructions) blocks.push({ title: "Instructions", body: content.instructions, copy: true });
  if (content.usage) blocks.push({ title: "Usage", body: content.usage });

  const lists: { title: string; items: string[] }[] = [
    { title: "Inputs", items: content.inputs ?? [] },
    { title: "Outputs", items: content.outputs ?? [] },
    { title: "Dependencies", items: content.dependencies ?? [] },
    { title: "Works with", items: content.compatibility ?? [] },
  ].filter((list) => list.items.length > 0);

  if (!blocks.length && !lists.length && !content.examples?.length && !content.documentation) {
    return null;
  }

  return (
    <div className="space-y-6">
      {blocks.map((block) => (
        <Panel key={block.title}>
          <PanelHeader className="flex flex-row items-center justify-between gap-3">
            <PanelTitle>{block.title}</PanelTitle>
            {block.copy ? (
              <CopyButton value={block.body} ariaLabel={block.title.toLowerCase()} />
            ) : null}
          </PanelHeader>
          <PanelBody>
            <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-md border border-border bg-muted/30 p-4 font-mono text-xs leading-relaxed">
              {block.body}
            </pre>
          </PanelBody>
        </Panel>
      ))}

      {content.examples?.length ? (
        <Panel>
          <PanelHeader>
            <PanelTitle>Examples</PanelTitle>
          </PanelHeader>
          <PanelBody className="space-y-4">
            {content.examples.map((example, index) => (
              <div key={index}>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <p className="text-sm font-medium">{example.title || `Example ${index + 1}`}</p>
                  <CopyButton value={example.body} ariaLabel={example.title || `example ${index + 1}`} />
                </div>
                <pre className="overflow-auto whitespace-pre-wrap rounded-md border border-border bg-muted/30 p-3 font-mono text-xs">
                  {example.body}
                </pre>
              </div>
            ))}
          </PanelBody>
        </Panel>
      ) : null}

      {lists.length ? (
        <Panel>
          <PanelHeader>
            <PanelTitle>Details</PanelTitle>
          </PanelHeader>
          <PanelBody className="grid gap-5 sm:grid-cols-2">
            {lists.map((list) => (
              <div key={list.title}>
                <p className="mb-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                  {list.title}
                </p>
                <ul className="list-disc space-y-1 pl-5 text-sm">
                  {list.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ))}
          </PanelBody>
        </Panel>
      ) : null}

      {content.documentation ? (
        <Panel>
          <PanelHeader>
            <PanelTitle>Documentation</PanelTitle>
          </PanelHeader>
          <PanelBody>
            <div className="max-h-[40rem] overflow-auto text-sm leading-relaxed whitespace-pre-wrap">
              {content.documentation}
            </div>
          </PanelBody>
        </Panel>
      ) : null}
    </div>
  );
}

export function UseSection({ listing }: { listing: ListingDetail }) {
  const clone = listing.repositoryUrl
    ? `git clone ${listing.repositoryUrl}${
        listing.repositoryRef ? ` && cd ${repoDir(listing.repositoryUrl)} && git checkout ${listing.repositoryRef}` : ""
      }`
    : null;
  const configs = Object.entries(listing.installConfigs) as [
    InstallTarget,
    { config: Record<string, unknown>; warnings: string[] },
  ][];

  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>Use it</PanelTitle>
      </PanelHeader>
      <PanelBody className="space-y-6">
        <div>
          <p className="mb-2 text-sm font-medium">With Aevrin MCP</p>
          <p className="mb-3 text-sm text-muted-foreground">
            Connect Aevrin MCP once, and your agent can read this item and use it.
          </p>
          <AevrinMcpSnippet itemSlug={listing.slug} />
        </div>

        {clone ? (
          <div>
            <div className="mb-1 flex items-center justify-between gap-2">
              <p className="text-sm font-medium">Clone the repository</p>
              <CopyButton value={clone} ariaLabel="clone command" />
            </div>
            <pre className="overflow-x-auto rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-xs whitespace-pre-wrap break-all">
              {clone}
            </pre>
          </div>
        ) : null}

        {configs.length ? (
          <div className="space-y-4">
            <p className="text-sm font-medium">Add this server to your agent directly</p>
            {configs.map(([agent, { config, warnings }]) => {
              const text = JSON.stringify(config, null, 2);
              return (
                <div key={agent}>
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-muted-foreground">
                      {INSTALL_TARGET_LABELS[agent] ?? agent}
                    </span>
                    <CopyButton value={text} ariaLabel={`${INSTALL_TARGET_LABELS[agent] ?? agent} config`} />
                  </div>
                  <pre className="overflow-x-auto rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-xs">
                    {text}
                  </pre>
                  {warnings.length ? (
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
                      {warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : null}
      </PanelBody>
    </Panel>
  );
}

export function RelatedSection({ listing }: { listing: ListingDetail }) {
  if (!listing.related.length) return null;
  return (
    <Panel>
      <PanelHeader>
        <PanelTitle>Related</PanelTitle>
      </PanelHeader>
      <PanelBody className="grid gap-3 sm:grid-cols-2">
        {listing.related.map((item) => (
          <Link
            key={item.id}
            href={`/marketplace/${item.slug}`}
            className="rounded-lg border border-border p-3 transition-colors hover:border-foreground/30 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-sm font-medium">{item.title}</span>
              <TypeBadge type={item.itemType} />
            </div>
            {item.relation === "uses" ? (
              <p className="mt-1 text-xs text-muted-foreground">Used by this item</p>
            ) : null}
            {item.description ? (
              <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.description}</p>
            ) : null}
          </Link>
        ))}
      </PanelBody>
    </Panel>
  );
}

function repoDir(url: string): string {
  return url.replace(/\/+$/, "").split("/").pop()?.replace(/\.git$/, "") || "repository";
}
