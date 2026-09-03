// Expected: 0 findings. Same shape as the vulnerable twin, hardcoded URL.

server.registerTool("healthcheck", {
  description: "Pings the fixed status endpoint",
  inputSchema: {}
}, async ({}) => {
  const response = await fetch("https://status.example.com/health");
  return { content: [{ type: "text", text: await response.text() }] };
});
