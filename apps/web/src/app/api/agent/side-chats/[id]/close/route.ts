import { NextRequest } from "next/server";
import { forwardConversationRequest } from "@/app/api/agent/conversations/_helpers";

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const path = `/api/v1/agent/side-chats/${encodeURIComponent(id)}/close`;
  return forwardConversationRequest(request, path, "POST");
}
