import { NextRequest } from "next/server";
import { forwardConversationRequest } from "../_helpers";

type Context = { params: Promise<{ id: string }> };

export async function GET(request: NextRequest, context: Context): Promise<Response> {
  const { id } = await context.params;
  return forwardConversationRequest(request, `/api/v1/agent/conversations/${encodeURIComponent(id)}`, "GET");
}

export async function PATCH(request: NextRequest, context: Context): Promise<Response> {
  const { id } = await context.params;
  return forwardConversationRequest(request, `/api/v1/agent/conversations/${encodeURIComponent(id)}`, "PATCH");
}
