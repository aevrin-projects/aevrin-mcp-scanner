// Expected: 4 findings, mcp-tool-input-reaches-shell-ts - one per handler
// shape the MCP TS SDK actually uses.

import { execSync } from "child_process";

server.registerTool("run_command", {
  description: "Runs a shell command",
  inputSchema: { command: z.string() }
}, async ({ command }) => {
  const result = execSync(command);
  return { content: [{ type: "text", text: result.toString() }] };
});

server.registerTool("run_command_props", {
  description: "Runs a shell command, property-accessed argument",
  inputSchema: { command: z.string() }
}, async (args) => {
  const cmd = args.command;
  const result = execSync(cmd);
  return { content: [{ type: "text", text: result.toString() }] };
});

server.tool("run_command_old_form", "Runs a shell command", { command: z.string() }, async ({ command }) => {
  const result = execSync(command);
  return { content: [{ type: "text", text: result.toString() }] };
});

server.tool("run_command_old_form_sync", "Runs a shell command", { command: z.string() }, ({ command }) => {
  const result = execSync(command);
  return { content: [{ type: "text", text: result.toString() }] };
});
