import { NextRequest, NextResponse } from "next/server";

import { authenticate } from "@/app/api/projects/_helpers";
import { serverEnv } from "@/lib/server-env";

export const dynamic = "force-dynamic";

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function viewerFailure(status: number, message: string, requestId: string, sessionId?: string, mode?: string) {
  const nonce = crypto.randomUUID();
  const notification = sessionId && mode ? `<script nonce="${nonce}">parent.postMessage(${JSON.stringify({ source: "careeract-browser-viewer", sessionId, mode, status: "error" })}, location.origin);</script>` : "";
  return new NextResponse(`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>浏览器窗口不可用</title></head><body><main><h1>浏览器窗口不可用</h1><p>${message}</p><a href="/inbox" target="_top">返回招聘沟通</a></main>${notification}</body></html>`, {
    status,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Request-ID": requestId,
      "Content-Security-Policy": `default-src 'none'; script-src 'nonce-${nonce}'; frame-ancestors 'self'; base-uri 'none'`,
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ sessionId: string }> },
) {
  const requestId = crypto.randomUUID();
  const { sessionId } = await context.params;
  if (!uuidPattern.test(sessionId)) {
    return viewerFailure(422, "浏览器会话标识无效。", requestId);
  }
  const auth = await authenticate(request, requestId);
  const requestUrl = new URL(request.url);
  const pageId = requestUrl.searchParams.get("pageId");
  const mode = requestUrl.searchParams.get("mode") ?? "control";
  if (mode !== "control" && mode !== "watch") {
    return viewerFailure(422, "浏览器观看模式无效。", requestId);
  }
  if ("response" in auth) return viewerFailure(auth.response.status, "CareerAct 登录已失效，请返回产品重新登录。", requestId, sessionId, mode);
  if (pageId !== null && (pageId.length === 0 || pageId.length > 256 || /[\u0000-\u001f]/u.test(pageId))) {
    return viewerFailure(422, "浏览器页面标识无效。", requestId, sessionId, mode);
  }
  const target = new URL(`/api/v1/browser/sessions/${sessionId}/viewer`, serverEnv.apiBaseUrl);
  if (pageId !== null) target.searchParams.set("pageId", pageId);
  target.searchParams.set("mode", mode);
  try {
    const upstream = await fetch(target, {
      headers: { Authorization: `Bearer ${auth.token}`, "X-Request-ID": requestId },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(25_000)]),
    });
    if (upstream.status === 401 || upstream.status === 403) {
      return viewerFailure(upstream.status, upstream.status === 401 ? "CareerAct 身份验证失败，请返回产品重新登录。" : "本次浏览器访问授权已失效或不可用，请返回招聘沟通重新读取并结束旧窗口。", requestId, sessionId, mode);
    }
    if (upstream.status !== 200) {
      const status = [404, 409, 422, 503].includes(upstream.status) ? upstream.status : 502;
      const message = status === 409 ? "浏览器正在被使用或结束，请返回招聘沟通重新读取状态。" : "浏览器窗口暂不可用，请返回招聘沟通重新读取状态。";
      return viewerFailure(status, message, requestId, sessionId, mode);
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
    return viewerFailure(502, "浏览器窗口暂不可用，请返回招聘沟通重新读取状态。", requestId, sessionId, mode);
  }
}
