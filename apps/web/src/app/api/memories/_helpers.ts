import { NextRequest, NextResponse } from "next/server";

import { getAuth } from "@/lib/auth";
import { serverEnv } from "@/lib/server-env";

type AuthResult = { token: string } | { response: Response };

export function failure(status: number, code: string, message: string, requestId: string) {
  return NextResponse.json(
    { error: { code, message, request_id: requestId } },
    { status, headers: { "Cache-Control": "no-store", "X-Request-ID": requestId } },
  );
}

export async function authenticate(request: NextRequest, requestId: string): Promise<AuthResult> {
  const session = await getAuth().api.getSession({ headers: request.headers });
  if (!session) return { response: failure(401, "unauthorized", "登录已失效，请重新登录。", requestId) };
  const { token } = await getAuth().api.getToken({ headers: request.headers });
  if (!token) return { response: failure(401, "unauthorized", "登录验证失败，请重新登录。", requestId) };
  return { token };
}

export function hasTrustedOrigin(request: NextRequest): boolean {
  return request.headers.get("origin") === new URL(serverEnv.betterAuthUrl).origin;
}

export async function readJsonBody(request: NextRequest, requestId: string): Promise<string | Response> {
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return failure(415, "invalid_content_type", "请使用 JSON 保存规则或笔记。", requestId);
  }
  const reader = request.body?.getReader();
  if (!reader) return failure(400, "missing_body", "缺少规则或笔记内容。", requestId);
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 131_072) {
        await reader.cancel();
        return failure(413, "memory_too_large", "规则或笔记过大，请精简内容。", requestId);
      }
      chunks.push(value);
    }
  } catch (error) {
    if (!(error instanceof TypeError || error instanceof DOMException)) throw error;
    return failure(400, "invalid_body", "未能读取规则或笔记内容，请检查连接。", requestId);
  } finally {
    reader.releaseLock();
  }
  return Buffer.concat(chunks).toString("utf8");
}

export async function forwardMemoryRequest(
  request: NextRequest,
  path: string,
  method: "GET" | "POST" | "PATCH",
): Promise<Response> {
  const requestId = crypto.randomUUID();
  if (method !== "GET" && !hasTrustedOrigin(request)) {
    return failure(403, "forbidden", "请求来源无效，请从工作台保存。", requestId);
  }
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
      method,
      headers: {
        Authorization: `Bearer ${auth.token}`,
        "Content-Type": "application/json",
        "X-Request-ID": requestId,
      },
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(15_000)]),
    });
    if (upstream.status === 401 || upstream.status === 403) {
      return failure(upstream.status, "unauthorized", "登录验证失败，请重新登录。", requestId);
    }
    if (![200, 201, 404, 409, 422, 503].includes(upstream.status)) {
      return failure(502, "memory_unavailable", "规则与笔记暂时不可用，请稍后读取并核对。", requestId);
    }
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store", "X-Request-ID": requestId },
    });
  } catch (error) {
    if (!(error instanceof TypeError || error instanceof DOMException)) throw error;
    return failure(502, "memory_unavailable", "未能确认请求结果，请重新读取规则与笔记核对。", requestId);
  }
}

export function validMemoryId(memoryId: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(memoryId);
}
