import { NextRequest } from "next/server";
import { forwardConversationRequest } from "@/app/api/agent/conversations/_helpers";

export function POST(request: NextRequest) {
  return forwardConversationRequest(request, "/api/v1/agent/side-chats", "POST");
}
