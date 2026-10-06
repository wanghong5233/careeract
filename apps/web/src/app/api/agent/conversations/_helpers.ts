import { NextRequest } from "next/server";
import { authenticate, failure, hasTrustedOrigin, readJsonBody } from "@/app/api/projects/_helpers";
import { serverEnv } from "@/lib/server-env";

export async function forwardConversationRequest(request: NextRequest, path: string, method: "GET" | "POST" | "PATCH" | "DELETE"): Promise<Response> {
  const requestId = crypto.randomUUID();
  if (method !== "GET" && !hasTrustedOrigin(request)) return failure(403, "forbidden", "请求来源无效。", requestId);
  const auth = await authenticate(request, requestId);
  if ("response" in auth) return auth.response;
  let body: string | undefined;
  if (method !== "GET") {
    const content = await readJsonBody(request, requestId);
    if (content instanceof Response) return content;
    body = content;
  }
  try {
    const upstream = await fetch(new URL(path, serverEnv.apiBaseUrl), {
      method, body, cache: "no-store", redirect: "error",
      headers: { Authorization: `Bearer ${auth.token}`, "Content-Type": "application/json", "X-Request-ID": requestId },
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(15_000)]),
    });
    if (![200, 201, 401, 403, 404, 409, 422, 503].includes(upstream.status)) return failure(502, "conversation_unavailable", "对话服务暂不可用，请重新读取核对。", requestId);
    return new Response(upstream.body, { status: upstream.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store", "X-Request-ID": requestId } });
  } catch (error) {
    if (!(error instanceof TypeError || error instanceof DOMException)) throw error;
    if (request.signal.aborted) return new Response(null, { status: 499 });
    return failure(502, "conversation_unavailable", "未能确认请求结果，请重新读取对话核对。", requestId);
  }
}
