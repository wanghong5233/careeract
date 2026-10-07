import { NextRequest } from "next/server";

import { forward } from "./_helpers";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return forward(request, "/api/v1/connections/boss", "GET");
}

export async function POST(request: NextRequest) {
  return forward(request, "/api/v1/connections/boss", "POST");
}
