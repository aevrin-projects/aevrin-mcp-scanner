export const OWASP_CATEGORY_LABELS: Record<string, string> = {
  MCP01: "Token Mismanagement & Secret Exposure",
  MCP02: "Tool Poisoning (Hidden Instructions)",
  MCP03: "Cross-Origin Escalation / Tool Shadowing",
  MCP04: "Rug Pull (Tool Drift After Install)",
  MCP05: "Command Injection, Path Traversal, SSRF, File Access",
  MCP06: "Missing/Weak Authentication",
  MCP07: "Supply Chain / Malicious or Typosquatted Dependencies",
  MCP08: "Prompt Injection via Live Tool Responses",
  MCP09: "Excessive Agency / Overprivileged Scope",
  MCP10: "Weak/Missing Audit Logging",
};
