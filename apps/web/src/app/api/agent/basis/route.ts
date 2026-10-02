import { NextRequest, NextResponse } from "next/server";

import { getAuth } from "@/lib/auth";
import { agentThreadId } from "@/lib/agent-session";
import { serverEnv } from "@/lib/server-env";

export async function GET(request: NextRequest): Promise<Response> {
  const requestId = crypto.randomUUID();
  const headers = { "Cache-Control": "no-store", "X-Request-ID": requestId };
  const auth = getAuth();
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session) return NextResponse.json({ error: { message: "登录已失效。", code: "unauthorized", request_id: requestId } }, { status: 401, headers });
  const { token } = await auth.api.getToken({ headers: request.headers });
  const url = new URL("/api/v1/agent/session/basis", serverEnv.apiBaseUrl);
  url.searchParams.set("session_id", agentThreadId(session.user.id));
  try {
    const upstream = await fetch(url, {
      headers: { Authorization: `Bearer ${token}`, "X-Request-ID": requestId },
      cache: "no-store", redirect: "error",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(15_000)]),
    });
    return new Response(upstream.body, { status: upstream.status, headers: { ...headers, "Content-Type": "application/json" } });
  } catch (error: unknown) {
    if (!(error instanceof TypeError || error instanceof DOMException)) throw error;
    return NextResponse.json({ error: { message: "本次依据暂时无法读取，请重试。", code: "agent_basis_unavailable", request_id: requestId } }, { status: 502, headers });
  }
}
