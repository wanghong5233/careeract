import { NextRequest } from "next/server";
import { forwardConversationRequest } from "@/app/api/agent/conversations/_helpers";

export async function GET(request: NextRequest): Promise<Response> {
  return forwardConversationRequest(request, "/api/v1/agent/model", "GET");
}
