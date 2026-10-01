import { NextRequest } from "next/server";

import { failure, forwardProjectRequest, validProjectId } from "../_helpers";

export const dynamic = "force-dynamic";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ projectId: string }> },
): Promise<Response> {
  const { projectId } = await params;
  if (!validProjectId(projectId)) return failure(404, "project_not_found", "找不到该职业项目。", crypto.randomUUID());
  return forwardProjectRequest(request, `/api/v1/projects/${projectId}`, "GET");
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ projectId: string }> },
): Promise<Response> {
  const { projectId } = await params;
  if (!validProjectId(projectId)) return failure(404, "project_not_found", "找不到该职业项目。", crypto.randomUUID());
  return forwardProjectRequest(request, `/api/v1/projects/${projectId}`, "PATCH");
}
