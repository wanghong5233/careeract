import { NextRequest, NextResponse } from "next/server";

import { getAuth } from "@/lib/auth";
import { agentThreadId } from "@/lib/agent-session";
import { serverEnv } from "@/lib/server-env";

function failure(status: number, code: string, message: string, requestId: string) {
  return NextResponse.json(
    { error: { code, message, request_id: requestId } },
    { status, headers: { "Cache-Control": "no-store", "X-Request-ID": requestId } },
  );
}

export async function PUT(request: NextRequest): Promise<Response> {
  const requestId = crypto.randomUUID();
  if (request.headers.get("origin") !== new URL(serverEnv.betterAuthUrl).origin) {
    return failure(403, "forbidden", "请求来源无效，请从工作台发送。", requestId);
  }
  const session = await getAuth().api.getSession({ headers: request.headers });
  if (!session) return failure(401, "unauthorized", "登录已失效，请重新登录。", requestId);
  let projectId: string | null = null;
  try {
    const body = await request.json() as { project_id?: unknown };
    if (body.project_id !== undefined && body.project_id !== null && typeof body.project_id !== "string") {
      return failure(422, "invalid_agent_session", "项目关联无效。", requestId);
    }
    projectId = body.project_id === null || body.project_id === undefined ? null : body.project_id;
  } catch {
    return failure(400, "invalid_body", "无法读取伙伴工作关联。", requestId);
  }
  const { token } = await getAuth().api.getToken({ headers: request.headers });
  try {
    const upstream = await fetch(new URL("/api/v1/agent/session", serverEnv.apiBaseUrl), {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "X-Request-ID": requestId,
      },
      body: JSON.stringify({ session_id: agentThreadId(session.user.id), project_id: projectId }),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(15_000)]),
    });
    if (![200, 404, 409, 422, 503].includes(upstream.status)) {
      return failure(502, "agent_session_unavailable", "伙伴工作暂时无法保存，请稍后重试。", requestId);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store", "X-Request-ID": requestId },
    });
  } catch {
    if (request.signal.aborted) return new Response(null, { status: 499 });
    return failure(502, "agent_session_unavailable", "伙伴工作暂时无法保存，请稍后重试。", requestId);
  }
}
