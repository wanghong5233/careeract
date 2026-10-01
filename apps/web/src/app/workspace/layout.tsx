import { createHash } from "node:crypto";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { WorkspaceFrame } from "@/components/workspace-frame";
import { getAuth } from "@/lib/auth";
import { serverEnv } from "@/lib/server-env";

export const dynamic = "force-dynamic";

function agentThreadId(userId: string): string {
  const digest = createHash("sha256")
    .update(`careeract:workspace-agent:${serverEnv.betterAuthSecret}:${userId}`)
    .digest("hex")
    .slice(0, 32);
  return `${digest.slice(0, 8)}-${digest.slice(8, 12)}-4${digest.slice(13, 16)}-${(8 + (Number.parseInt(digest[16], 16) % 4)).toString(16)}${digest.slice(17, 20)}-${digest.slice(20)}`;
}

export default async function WorkspaceLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (!session) redirect("/sign-in");
  return <WorkspaceFrame agentThreadId={agentThreadId(session.user.id)}>{children}</WorkspaceFrame>;
}
