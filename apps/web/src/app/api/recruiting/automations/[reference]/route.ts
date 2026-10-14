import { NextRequest } from "next/server";
import { forward } from "@/app/api/connections/boss/_helpers";

export async function DELETE(request: NextRequest, context: { params: Promise<{ reference: string }> }) {
  const { reference } = await context.params;
  return forward(request, `/api/v1/recruiting/automations/${encodeURIComponent(reference)}`, "DELETE", 60_000);
}
