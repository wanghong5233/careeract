import { notFound } from "next/navigation";

import { WorkspaceProjectDetail } from "@/components/workspace-projects";

export default async function ProjectRoute({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(projectId)) notFound();
  return <WorkspaceProjectDetail key={projectId} projectId={projectId} />;
}
