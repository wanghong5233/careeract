import { NextRequest } from "next/server";

import { failure, validProjectId } from "@/app/api/projects/_helpers";
import { forward } from "../../_helpers";

type Context = { params: Promise<{ connectionId: string }> };

async function loginRequest(request: NextRequest, context: Context, method: "GET" | "POST" | "DELETE") {
  const { connectionId } = await context.params;
  if (!validProjectId(connectionId)) {
    return failure(422, "invalid_boss_connection", "连接标识无效。", crypto.randomUUID());
  }
  return forward(request, `/api/v1/connections/boss/${connectionId}/login`, method, method === "GET" ? 15_000 : 60_000);
}

export async function GET(request: NextRequest, context: Context) {
  return loginRequest(request, context, "GET");
}

export async function POST(request: NextRequest, context: Context) {
  return loginRequest(request, context, "POST");
}

export async function DELETE(request: NextRequest, context: Context) {
  return loginRequest(request, context, "DELETE");
}
