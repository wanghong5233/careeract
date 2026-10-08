import { NextRequest, NextResponse } from "next/server";

import { authenticate, failure, hasTrustedOrigin, validProjectId } from "@/app/api/projects/_helpers";
import { serverEnv } from "@/lib/server-env";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ sessionId: string }> },
) {
  const requestId = crypto.randomUUID();
  if (!hasTrustedOrigin(request)) {
    return failure(403, "untrusted_origin", "请求来源无效。", requestId);
  }
  const { sessionId } = await context.params;
  if (!validProjectId(sessionId)) {
    return failure(422, "invalid_browser_session", "浏览器会话标识无效。", requestId);
  }
  const auth = await authenticate(request, requestId);
  if ("response" in auth) return auth.response;
  try {
    const upstream = await fetch(new URL(`/api/v1/browser/sessions/${sessionId}/viewer-renew`, serverEnv.apiBaseUrl), {
      method: "POST",
      headers: { Authorization: `Bearer ${auth.token}`, "X-Request-ID": requestId, "Content-Type": "application/json" },
      body: "{}",
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(8_000)]),
    });
    if (upstream.status !== 204) {
      const status = [401, 403, 404, 409].includes(upstream.status) ? upstream.status : 503;
      return failure(status, "browser_viewer_unavailable", "登录浏览器已断开，请返回重新读取状态。", requestId);
    }
    return new NextResponse(null, { status: 204, headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (!(error instanceof TypeError || error instanceof DOMException)) throw error;
    return failure(503, "browser_viewer_unavailable", "登录浏览器续期暂不可用。", requestId);
  }
}
