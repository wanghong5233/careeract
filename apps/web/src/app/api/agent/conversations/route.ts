import { NextRequest } from "next/server";
import { forwardConversationRequest } from "./_helpers";

export async function GET(request: NextRequest): Promise<Response> {
  return forwardConversationRequest(request, `/api/v1/agent/conversations${request.nextUrl.search}`, "GET");
}

export async function POST(request: NextRequest): Promise<Response> {
  return forwardConversationRequest(request, "/api/v1/agent/conversations", "POST");
}
