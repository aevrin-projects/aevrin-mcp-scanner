import type { Metadata } from "next";

import { ListingDetailPage } from "@/views/marketplace-detail";

export const metadata: Metadata = {
  title: "Aevrin Registry",
  description:
    "What this item is, how to use it with your agent, and, for an MCP server, its Aevrin security grade.",
};

export default async function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <ListingDetailPage slug={slug} />;
}
