import { NextRequest } from "next/server";

import { failure } from "@/app/api/projects/_helpers";
import { forward } from "../_helpers";

export async function DELETE(request: NextRequest, context: { params: Promise<{ connectionId: string }> }) {
  const { connectionId } = await context.params;
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(connectionId)) {
    return failure(422, "invalid_boss_connection", "连接标识无效。", crypto.randomUUID());
  }
  return forward(request, `/api/v1/connections/boss/${connectionId}`, "DELETE");
}
