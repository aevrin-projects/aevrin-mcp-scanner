// Expected: 0 findings. Same shape as the vulnerable twin, hardcoded path.

import * as fs from "fs";

server.registerTool("read_config", {
  description: "Reads the fixed server config",
  inputSchema: {}
}, async ({}) => {
  const data = fs.readFileSync("./config.json");
  return { content: [{ type: "text", text: data.toString() }] };
});
