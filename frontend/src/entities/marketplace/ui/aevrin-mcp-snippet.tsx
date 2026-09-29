import { CopyButton } from "@/shared/ui/copy-button";

/**
 * How to give an agent the Aevrin Registry.
 *
 * One component, used on the browse page and on every item, so the endpoint
 * and the config shape exist in exactly one place in the frontend. The config
 * uses `"type": "http"`, Claude Code's canonical name for streamable HTTP; a
 * `url` with no `type` is read as a stdio server and skipped.
 */

export const AEVRIN_MCP_URL = "https://api.mcp.aevrin.net/mcp";

const ADD_COMMAND = `claude mcp add --scope user --transport http aevrin ${AEVRIN_MCP_URL}`;

const CONFIG = JSON.stringify(
  { mcpServers: { aevrin: { type: "http", url: AEVRIN_MCP_URL } } },
  null,
  2,
);

export function AevrinMcpSnippet({ itemSlug }: { itemSlug?: string }) {
  // With an item, the instruction names it, so the agent reads this exact
  // entry rather than searching for something like it.
  const instruction = itemSlug
    ? `Use the Aevrin registry item "${itemSlug}" (get_registry_item) to help with this task.`
    : null;

  return (
    <div className="space-y-3 text-sm">
      <Snippet label="Claude Code" value={ADD_COMMAND} />
      <Snippet label="Any MCP client (.mcp.json)" value={CONFIG} multiline />
      {instruction ? <Snippet label="Then ask your agent" value={instruction} /> : null}
    </div>
  );
}

function Snippet({ label, value, multiline = false }: { label: string; value: string; multiline?: boolean }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <CopyButton value={value} ariaLabel={label} />
      </div>
      <pre
        className={`overflow-x-auto rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-xs ${
          multiline ? "" : "whitespace-pre-wrap break-all"
        }`}
      >
        {value}
      </pre>
    </div>
  );
}
