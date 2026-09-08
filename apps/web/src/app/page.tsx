import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { WorkspaceShell } from "@/components/workspace-shell";
import { getAuth } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function Home() {
  const session = await getAuth().api.getSession({ headers: await headers() });
  if (!session) {
    redirect("/sign-in");
  }
  return <WorkspaceShell />;
}
