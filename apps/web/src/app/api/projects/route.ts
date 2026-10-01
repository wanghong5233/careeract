import { NextRequest } from "next/server";

import { forwardProjectRequest } from "./_helpers";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  return forwardProjectRequest(request, `/api/v1/projects${request.nextUrl.search}`, "GET");
}

export async function POST(request: NextRequest): Promise<Response> {
  return forwardProjectRequest(request, "/api/v1/projects", "POST");
}
