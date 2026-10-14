import { NextRequest } from "next/server";
import { forward } from "@/app/api/connections/boss/_helpers";

export async function GET(request: NextRequest) {
  const query = new URLSearchParams();
  for (const name of ["connection_id", "cursor"]) {
    const value = request.nextUrl.searchParams.get(name);
    if (value) query.set(name, value);
  }
  return forward(request, `/api/v1/recruiting/replies?${query}`, "GET");
}

export async function POST(request: NextRequest) {
  return forward(request, "/api/v1/recruiting/replies", "POST", 25_000);
}
