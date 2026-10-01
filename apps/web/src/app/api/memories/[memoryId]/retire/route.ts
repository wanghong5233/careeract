import { NextRequest } from "next/server";

import { failure, forwardMemoryRequest, validMemoryId } from "../../_helpers";

type Context = { params: Promise<{ memoryId: string }> };

export async function POST(request: NextRequest, context: Context): Promise<Response> {
  const { memoryId } = await context.params;
  if (!validMemoryId(memoryId)) return failure(404, "memory_not_found", "找不到该规则或笔记。", crypto.randomUUID());
  return forwardMemoryRequest(request, `/api/v1/memories/${memoryId}/retire`, "POST");
}
