import { notFound } from "next/navigation";

import { ProfileEditor } from "@/components/profile-editor";
import { WorkspaceSectionPage } from "@/components/workspace-pages";
import { workspaceSections, type WorkspaceSection } from "@/components/workspace-sections";

export default async function AgentSectionRoute({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  if (!workspaceSections.some(item => item.key === section)) notFound();
  if (section === "background") return <ProfileEditor />;
  return <WorkspaceSectionPage section={section as WorkspaceSection} />;
}
