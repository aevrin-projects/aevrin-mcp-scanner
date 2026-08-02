import { ScanDetailClient } from "./scan-detail-client";

export default async function ScanDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ScanDetailClient scanId={id} />;
}
