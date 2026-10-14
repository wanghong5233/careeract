import { NextRequest } from "next/server";
import { forward } from "@/app/api/connections/boss/_helpers";

export async function POST(request: NextRequest, context: { params: Promise<{ reference: string }> }) {
  const { reference } = await context.params;
  return forward(request, `/api/v1/recruiting/automations/${encodeURIComponent(reference)}/dispatch`, "POST", 25_000);
}
