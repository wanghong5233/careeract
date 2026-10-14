import { NextRequest } from "next/server";
import { failure, validProjectId } from "@/app/api/projects/_helpers";
import { forward } from "@/app/api/connections/boss/_helpers";

export async function replyRequest(request: NextRequest, context: { params: Promise<{ replyId: string }> }, method: "GET" | "POST" | "DELETE", resume = false, suffix = "") {
  const { replyId } = await context.params;
  if (!validProjectId(replyId)) return failure(422, "invalid_reply_id", "回复任务标识无效。", crypto.randomUUID());
  return forward(request, `/api/v1/recruiting/replies/${replyId}${resume ? "/resume" : suffix}`, method, method === "POST" ? 25_000 : 15_000);
}
