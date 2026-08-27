import type { Metadata } from "next";

import { ListingDetailPage } from "@/views/marketplace-detail";

export const metadata: Metadata = {
  title: "MCP server: Aevrin Marketplace",
  description:
    "Security grade, scan coverage, source, capabilities, and installation for this MCP server.",
};

export default async function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <ListingDetailPage slug={slug} />;
}
