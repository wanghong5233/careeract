import { NextRequest } from "next/server";
import { forwardConversationRequest } from "@/app/api/agent/conversations/_helpers";

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  return forwardConversationRequest(request, `/api/v1/agent/conversations/${encodeURIComponent(id)}/branch`, "POST");
}
