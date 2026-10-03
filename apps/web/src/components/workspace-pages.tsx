import { WorkspaceSurface } from "@/components/workspace-surfaces";
import { workspaceSections, type WorkspaceSection } from "@/components/workspace-sections";

export function WorkspaceHome() {
  return null;
}

export function WorkspaceSectionPage({ section }: { section: WorkspaceSection }) {
  const item = workspaceSections.find(candidate => candidate.key === section);
  if (!item) return null;
  return <WorkspaceSurface section={section} />;
}
