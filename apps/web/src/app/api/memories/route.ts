import { NextRequest } from "next/server";

import { forwardMemoryRequest } from "./_helpers";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  return forwardMemoryRequest(request, `/api/v1/memories${request.nextUrl.search}`, "GET");
}

export async function POST(request: NextRequest): Promise<Response> {
  return forwardMemoryRequest(request, "/api/v1/memories", "POST");
}
