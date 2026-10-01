import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { WorkspaceFrame } from "@/components/workspace-frame";
import { getAuth } from "@/lib/auth";
import { agentThreadId } from "@/lib/agent-session";

export const dynamic = "force-dynamic";

export default async function WorkspaceLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (!session) redirect("/sign-in");
  return <WorkspaceFrame agentThreadId={agentThreadId(session.user.id)}>{children}</WorkspaceFrame>;
}
