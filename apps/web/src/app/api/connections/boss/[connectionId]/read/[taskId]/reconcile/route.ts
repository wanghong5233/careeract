import { NextRequest } from "next/server";
import { readRequest, type ReadContext } from "../../_helpers";

export async function POST(request: NextRequest, context: ReadContext) {
  return readRequest(request, context, "POST", "reconcile");
}
