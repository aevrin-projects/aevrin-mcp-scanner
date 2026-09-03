// Expected: 0 findings. Same shape as the vulnerable twin, hardcoded command.

import { execSync } from "child_process";

server.registerTool("get_uptime", {
  description: "Returns the host's uptime",
  inputSchema: {}
}, async ({}) => {
  const result = execSync("uptime");
  return { content: [{ type: "text", text: result.toString() }] };
});
