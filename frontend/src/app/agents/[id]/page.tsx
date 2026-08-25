import { AgentDetailPage } from "@/views/agent-detail";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AgentDetailPage agentId={id} />;
}
