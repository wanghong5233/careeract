import { NextRequest } from "next/server";
import { readRequest, type ReadContext } from "../_helpers";

export async function GET(request: NextRequest, context: ReadContext) {
  return readRequest(request, context, "GET", "task");
}

export async function DELETE(request: NextRequest, context: ReadContext) {
  return readRequest(request, context, "DELETE", "task");
}
