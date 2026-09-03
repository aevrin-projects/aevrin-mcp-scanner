// Expected: 2 findings, mcp-tool-input-reaches-network-request-ts.

server.registerTool("fetch_url", {
  description: "Fetches content from a URL",
  inputSchema: { url: z.string() }
}, async ({ url }) => {
  const response = await fetch(url);
  const text = await response.text();
  return { content: [{ type: "text", text }] };
});

server.registerTool("axios_get", {
  description: "Fetches content via axios",
  inputSchema: { url: z.string() }
}, async ({ url }) => {
  const response = await axios.get(url);
  return { content: [{ type: "text", text: response.data }] };
});
