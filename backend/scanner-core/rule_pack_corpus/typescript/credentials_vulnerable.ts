// Expected: 3 findings, mcp-tool-handler-reads-credential-path-ts.

import * as fs from "fs";

server.registerTool("read_aws_creds", {
  description: "Reads the AWS credentials file",
  inputSchema: {}
}, async ({}) => {
  const data = fs.readFileSync("~/.aws/credentials");
  return { content: [{ type: "text", text: data.toString() }] };
});

server.registerTool("get_api_key", {
  description: "Returns the configured API key",
  inputSchema: {}
}, async ({}) => {
  const key = process.env["API_KEY"];
  return { content: [{ type: "text", text: key }] };
});

server.registerTool("get_secret_dot", {
  description: "Returns a secret via dot access",
  inputSchema: {}
}, async ({}) => {
  const secret = process.env.MY_SECRET_TOKEN;
  return { content: [{ type: "text", text: secret }] };
});
