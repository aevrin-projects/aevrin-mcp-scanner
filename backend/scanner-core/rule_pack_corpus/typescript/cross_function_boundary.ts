// Expected: 0 findings. Documents the pack's known, disclosed limitation:
// Semgrep's open-source engine cannot track taint across a function
// boundary, so a sink reached only through a helper the tool handler calls
// is missed. This fixture pins that the pack does NOT accidentally start
// catching this case (which would mean something else changed and needs
// re-verifying), not that this is desirable.

import { execSync } from "child_process";

function runIt(cmd: string) {
  return execSync(cmd);
}

server.registerTool("run_command", {
  description: "Runs a shell command via a helper function",
  inputSchema: { command: z.string() }
}, async ({ command }) => {
  const result = runIt(command);
  return { content: [{ type: "text", text: result.toString() }] };
});
