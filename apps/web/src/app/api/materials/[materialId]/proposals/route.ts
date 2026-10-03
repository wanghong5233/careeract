import { NextRequest } from "next/server";

import { failure, forwardMaterialRequest, validMaterialId } from "../../_helpers";

export const dynamic = "force-dynamic";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ materialId: string }> },
): Promise<Response> {
  const { materialId } = await context.params;
  if (!validMaterialId(materialId)) return failure(404, "material_not_found", "找不到该材料。", crypto.randomUUID());
  return forwardMaterialRequest(request, `/api/v1/materials/${materialId}/proposals`, "POST");
}
