import type { Metadata } from "next";

export { SubmitPage as default } from "@/views/marketplace-submit";

export const metadata: Metadata = {
  title: "Submit an MCP server: Aevrin",
  description:
    "Submit an MCP server for the Aevrin marketplace. Paste a URL; Aevrin derives the metadata and scans it before publication.",
};
