// Expected: 0 findings. path.basename() is a modeled sanitizer for all
// three filesystem rules.

import * as fs from "fs";
import * as path from "path";

server.registerTool("write_report", {
  description: "Writes a report, filename basename only",
  inputSchema: { filename: z.string(), content: z.string() }
}, async ({ filename, content }) => {
  const safeName = path.basename(filename);
  fs.writeFileSync(safeName, content);
  return { content: [{ type: "text", text: "ok" }] };
});
