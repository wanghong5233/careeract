import { NextRequest } from "next/server";

import { failure, validProjectId } from "@/app/api/projects/_helpers";
import { forward } from "../../_helpers";

export type ReadContext = { params: Promise<{ connectionId: string; taskId?: string }> };

export async function readRequest(request: NextRequest, context: ReadContext, method: "GET" | "POST" | "DELETE", operation?: "task" | "run" | "result" | "reconcile") {
  const { connectionId, taskId } = await context.params;
  if (!validProjectId(connectionId) || (operation && (!taskId || !validProjectId(taskId)))) {
    return failure(422, "invalid_read_execution", "读取任务标识无效。", crypto.randomUUID());
  }
  const suffix = operation ? `/${taskId}${operation === "task" ? "" : `/${operation}`}` : "";
  return forward(request, `/api/v1/connections/boss/${connectionId}/read${suffix}`, method, operation === "run" ? 120_000 : 15_000);
}
