import { source } from "@/lib/source";

export const revalidate = false;

export async function GET() {
  const pages = source.getPages();
  const lines = [
    "# Aevrin",
    "",
    "> Aevrin scans Model Context Protocol (MCP) servers for security risks — via a CLI, a " +
      "Claude Code hook, and a web dashboard at mcp.aevrin.net.",
    "",
    "## Docs",
    "",
    ...pages.map((page) => `- [${page.data.title}](https://docs.mcp.aevrin.net${page.url}): ${page.data.description ?? ""}`),
  ];

  return new Response(lines.join("\n"), {
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}
