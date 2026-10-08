import { NextRequest } from "next/server";

import { failure, validProjectId } from "@/app/api/projects/_helpers";
import { forward } from "../../../_helpers";

type Context = { params: Promise<{ connectionId: string }> };

export async function POST(request: NextRequest, context: Context) {
  const { connectionId } = await context.params;
  if (!validProjectId(connectionId)) {
    return failure(422, "invalid_boss_connection", "连接标识无效。", crypto.randomUUID());
  }
  return forward(request, `/api/v1/connections/boss/${connectionId}/login/finish`, "POST", 60_000);
}
