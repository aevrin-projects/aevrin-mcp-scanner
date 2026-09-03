// Expected: 3 findings - write, read, destructive, one per tool.

import * as fs from "fs";

server.registerTool("write_file", {
  description: "Writes content to a file",
  inputSchema: { path: z.string(), content: z.string() }
}, async ({ path, content }) => {
  fs.writeFileSync(path, content);
  return { content: [{ type: "text", text: "ok" }] };
});

server.registerTool("read_file", {
  description: "Reads a file",
  inputSchema: { path: z.string() }
}, async ({ path }) => {
  const data = fs.readFileSync(path);
  return { content: [{ type: "text", text: data.toString() }] };
});

server.registerTool("delete_file", {
  description: "Deletes a file",
  inputSchema: { path: z.string() }
}, async ({ path }) => {
  fs.unlinkSync(path);
  return { content: [{ type: "text", text: "deleted" }] };
});
