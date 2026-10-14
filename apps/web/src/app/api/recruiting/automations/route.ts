import { NextRequest } from "next/server";
import { forward } from "@/app/api/connections/boss/_helpers";

export async function GET(request: NextRequest) {
  const query = new URLSearchParams();
  const connection = request.nextUrl.searchParams.get("connection_id");
  if (connection) query.set("connection_id", connection);
  return forward(request, `/api/v1/recruiting/automations?${query}`, "GET");
}

export async function POST(request: NextRequest) {
  return forward(request, "/api/v1/recruiting/automations", "POST", 25_000);
}
