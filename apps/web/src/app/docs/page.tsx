import type { Metadata } from "next";
import { InstallDocsSection } from "@/components/install-docs-section";
import { SiteFooter } from "@/components/site-footer";

export const metadata: Metadata = {
  title: "Documentation — Aevrin",
  description: "Install the Aevrin CLI, sign in securely, and configure the Claude Code hook.",
};

export default function DocsPage() {
  return (
    <div>
      <InstallDocsSection headingLevel="h1" />
      <SiteFooter />
    </div>
  );
}
