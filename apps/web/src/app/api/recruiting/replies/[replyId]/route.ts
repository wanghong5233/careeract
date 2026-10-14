import { NextRequest } from "next/server";
import { replyRequest } from "../_helpers";

type Context = { params: Promise<{ replyId: string }> };

export async function GET(request: NextRequest, context: Context) {
  return replyRequest(request, context, "GET");
}

export async function DELETE(request: NextRequest, context: Context) {
  return replyRequest(request, context, "DELETE");
}
