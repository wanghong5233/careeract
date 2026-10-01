import { createHash } from "node:crypto";

import { serverEnv } from "@/lib/server-env";

export function agentThreadId(userId: string): string {
  const digest = createHash("sha256")
    .update(`careeract:workspace-agent:${serverEnv.betterAuthSecret}:${userId}`)
    .digest("hex")
    .slice(0, 32);
  return `${digest.slice(0, 8)}-${digest.slice(8, 12)}-4${digest.slice(13, 16)}-${(8 + (Number.parseInt(digest[16], 16) % 4)).toString(16)}${digest.slice(17, 20)}-${digest.slice(20)}`;
}
