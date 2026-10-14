import { NextRequest } from "next/server";
import { replyRequest } from "../../../_helpers";

export async function POST(request: NextRequest, context: { params: Promise<{ replyId: string }> }) {
  return replyRequest(request, context, "POST", false, "/send/reconcile");
}
