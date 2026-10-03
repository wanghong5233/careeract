import { NextRequest } from "next/server";

import { forwardMaterialRequest } from "./_helpers";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  return forwardMaterialRequest(request, `/api/v1/materials${request.nextUrl.search}`, "GET");
}

export async function POST(request: NextRequest): Promise<Response> {
  return forwardMaterialRequest(request, "/api/v1/materials", "POST");
}
