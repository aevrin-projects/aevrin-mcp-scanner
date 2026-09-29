import type { Metadata } from "next";

import { ListingDetailPage } from "@/views/marketplace-detail";

export const metadata: Metadata = {
  title: "Aevrin Registry",
  description:
    "What this item is, where it came from, and how to use it with your agent.",
};

export default async function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <ListingDetailPage slug={slug} />;
}
