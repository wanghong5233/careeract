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

async function readSessionBody(request: NextRequest, requestId: string): Promise<{ projectId: string | null } | Response> {
  if (request.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase() !== "application/json") {
    return failure(415, "invalid_content_type", "请使用 JSON 保存项目关联。", requestId);
  }
  const reader = request.body?.getReader();
  if (!reader) return failure(400, "missing_body", "缺少项目关联内容。", requestId);
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 4096) {
        await reader.cancel();
        return failure(413, "content_too_large", "项目关联内容过大。", requestId);
      }
      chunks.push(value);
    }
    const body: unknown = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (!body || typeof body !== "object" || Array.isArray(body) || Object.keys(body).some(key => key !== "project_id")) {
      return failure(422, "invalid_agent_session", "项目关联无效。", requestId);
    }
    const projectId = (body as { project_id?: unknown }).project_id ?? null;
    if (projectId !== null && (typeof projectId !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(projectId))) {
      return failure(422, "invalid_agent_session", "项目关联无效。", requestId);
    }
    return { projectId };
  } catch (error) {
    if (!(error instanceof SyntaxError || error instanceof TypeError || error instanceof DOMException)) throw error;
    return failure(400, "invalid_body", "无法读取 Agent 项目关联。", requestId);
  } finally { reader.releaseLock(); }
}

export async function PUT(request: NextRequest): Promise<Response> {
  const requestId = crypto.randomUUID();
  if (request.headers.get("origin") !== new URL(serverEnv.betterAuthUrl).origin) {
    return failure(403, "forbidden", "请求来源无效，请从 CareerAct Agent 发送。", requestId);
  }
  const session = await getAuth().api.getSession({ headers: request.headers });
  if (!session) return failure(401, "unauthorized", "登录已失效，请重新登录。", requestId);
  const { token } = await getAuth().api.getToken({ headers: request.headers });
  if (!token) return failure(401, "unauthorized", "登录验证失败，请重新登录。", requestId);
  const body = await readSessionBody(request, requestId);
  if (body instanceof Response) return body;
  try {
    const upstream = await fetch(new URL("/api/v1/agent/session", serverEnv.apiBaseUrl), {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "X-Request-ID": requestId,
      },
      body: JSON.stringify({ session_id: agentThreadId(session.user.id), project_id: body.projectId }),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(15_000)]),
    });
    if (upstream.status === 401 || upstream.status === 403) {
      return failure(upstream.status, "unauthorized", "登录验证失败，请重新登录。", requestId);
    }
    if (![200, 404, 409, 422, 503].includes(upstream.status)) {
      return failure(502, "agent_session_unavailable", "Agent 工作暂时无法保存，请稍后重试。", requestId);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store", "X-Request-ID": requestId },
    });
  } catch (error) {
    if (!(error instanceof TypeError || error instanceof DOMException)) throw error;
    if (request.signal.aborted) return new Response(null, { status: 499 });
    return failure(502, "agent_session_unavailable", "Agent 项目关联暂时无法保存，请稍后读取核对。", requestId);
  }
}
