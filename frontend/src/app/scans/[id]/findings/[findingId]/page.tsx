import { FindingDetailClient } from "@/views/finding-detail";

export default async function FindingDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string; findingId: string }>;
  searchParams: Promise<{ returnTo?: string }>;
}) {
  const { id, findingId } = await params;
  const { returnTo } = await searchParams;
  return <FindingDetailClient scanId={id} findingId={findingId} returnTo={returnTo} />;
}
