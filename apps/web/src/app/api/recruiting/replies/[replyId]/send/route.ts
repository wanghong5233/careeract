import { NextRequest } from "next/server";
import { replyRequest } from "../../_helpers";

export async function GET(request: NextRequest, context: { params: Promise<{ replyId: string }> }) {
  return replyRequest(request, context, "GET", false, "/send");
}

export async function POST(request: NextRequest, context: { params: Promise<{ replyId: string }> }) {
  return replyRequest(request, context, "POST", false, "/send");
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ replyId: string }> }) {
  return replyRequest(request, context, "DELETE", false, "/send");
}
