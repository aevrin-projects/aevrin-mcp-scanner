import { FindingDetailClient } from "./finding-detail-client";

export default async function FindingDetailPage({
  params,
}: {
  params: Promise<{ id: string; findingId: string }>;
}) {
  const { id, findingId } = await params;
  return <FindingDetailClient scanId={id} findingId={findingId} />;
}
