// Expected: 0 findings. Same shape as the vulnerable twin, non-credential-shaped name.

server.registerTool("get_region", {
  description: "Returns the configured AWS region",
  inputSchema: {}
}, async ({}) => {
  const region = process.env["AWS_REGION"];
  return { content: [{ type: "text", text: region }] };
});
