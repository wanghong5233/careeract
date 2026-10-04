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

export async function GET(request: NextRequest): Promise<Response> {
  const requestId = crypto.randomUUID();
  const session = await getAuth().api.getSession({ headers: request.headers });
  if (!session) return failure(401, "unauthorized", "登录已失效，请重新登录。", requestId);
  const { token } = await getAuth().api.getToken({ headers: request.headers });
  if (!token) return failure(401, "unauthorized", "登录验证失败，请重新登录。", requestId);
  const sessionId = new URL(request.url).searchParams.get("session_id") ?? agentThreadId(session.user.id);
  const history = new URL("/api/v1/agent/session/history", serverEnv.apiBaseUrl);
  history.searchParams.set("session_id", sessionId);
  history.searchParams.set("limit", "100");
  try {
    const upstream = await fetch(history, {
      headers: { Authorization: `Bearer ${token}`, "X-Request-ID": requestId },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(15_000)]),
    });
    if (upstream.status === 401 || upstream.status === 403) {
      return failure(upstream.status, "unauthorized", "登录验证失败，请重新登录。", requestId);
    }
    if (![200, 404, 503].includes(upstream.status)) {
      return failure(502, "agent_history_unavailable", "Agent 历史暂时无法读取，请稍后重试。", requestId);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store", "X-Request-ID": requestId },
    });
  } catch (error) {
    if (!(error instanceof TypeError || error instanceof DOMException)) throw error;
    if (request.signal.aborted) return new Response(null, { status: 499 });
    return failure(502, "agent_history_unavailable", "Agent 历史暂时无法读取，请稍后重试。", requestId);
  }
}
