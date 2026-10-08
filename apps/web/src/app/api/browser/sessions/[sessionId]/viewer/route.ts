import { NextRequest, NextResponse } from "next/server";

import { authenticate, failure } from "@/app/api/projects/_helpers";
import { serverEnv } from "@/lib/server-env";

export const dynamic = "force-dynamic";

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ sessionId: string }> },
) {
  const requestId = crypto.randomUUID();
  const { sessionId } = await context.params;
  if (!uuidPattern.test(sessionId)) {
    return failure(422, "invalid_browser_session", "浏览器会话标识无效。", requestId);
  }
  const auth = await authenticate(request, requestId);
  if ("response" in auth) return auth.response;
  const pageId = request.nextUrl.searchParams.get("pageId");
  if (pageId !== null && (pageId.length === 0 || pageId.length > 256 || /[\u0000-\u001f]/u.test(pageId))) {
    return failure(422, "invalid_browser_page", "浏览器页面标识无效。", requestId);
  }
  const target = new URL(`/api/v1/browser/sessions/${sessionId}/viewer`, serverEnv.apiBaseUrl);
  if (pageId !== null) target.searchParams.set("pageId", pageId);
  try {
    const upstream = await fetch(target, {
      headers: { Authorization: `Bearer ${auth.token}`, "X-Request-ID": requestId },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(25_000)]),
    });
    if (upstream.status === 401 || upstream.status === 403) {
      return failure(upstream.status, "unauthorized", "登录验证失败，请重新登录。", requestId);
    }
    if (![200, 404, 409, 422, 503].includes(upstream.status)) {
      return failure(502, "browser_viewer_unavailable", "浏览器登录页面暂不可用，请重新读取状态。", requestId);
    }
    const headers = new Headers({
      "Content-Type": upstream.headers.get("content-type") ?? "text/html",
      "Cache-Control": "no-store",
      "X-Request-ID": requestId,
    });
    const cookie = upstream.headers.get("set-cookie");
    if (cookie) headers.set("set-cookie", cookie);
    return new NextResponse(upstream.body, { status: upstream.status, headers });
  } catch (error) {
    if (!(error instanceof TypeError || error instanceof DOMException)) throw error;
    return failure(502, "browser_viewer_unavailable", "浏览器登录页面暂不可用，请重新读取状态。", requestId);
  }
}
