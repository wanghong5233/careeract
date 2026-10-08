import { NextRequest, NextResponse } from "next/server";

import { authenticate, failure, hasTrustedOrigin } from "@/app/api/projects/_helpers";
import { serverEnv } from "@/lib/server-env";

async function readBody(request: NextRequest, requestId: string): Promise<string | Response> {
  if (request.headers.get("content-type")?.split(";", 1)[0].trim() !== "application/json" ||
      ![null, "identity"].includes(request.headers.get("content-encoding"))) {
    return failure(415, "invalid_content_type", "请使用 JSON 提交连接请求。", requestId);
  }
  const reader = request.body?.getReader();
  if (!reader) return failure(400, "missing_body", "缺少连接请求内容。", requestId);
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 1024) {
        await reader.cancel();
        return failure(413, "connection_too_large", "连接请求内容过大。", requestId);
      }
      chunks.push(value);
    }
    return Buffer.concat(chunks).toString("utf8");
  } catch (error) {
    if (!(error instanceof TypeError || error instanceof DOMException)) throw error;
    return failure(400, "invalid_body", "无法读取连接请求。", requestId);
  } finally {
    reader.releaseLock();
  }
}

export async function forward(request: NextRequest, path: string, method: "GET" | "POST" | "DELETE", timeout = 15_000) {
  const requestId = crypto.randomUUID();
  if (method !== "GET" && !hasTrustedOrigin(request)) {
    return failure(403, "forbidden", "请求来源无效，请从 CareerAct 招聘沟通发起。", requestId);
  }
  const auth = await authenticate(request, requestId);
  if ("response" in auth) return auth.response;
  let body: string | undefined;
  if (method !== "GET") {
    const content = await readBody(request, requestId);
    if (content instanceof Response) return content;
    body = content;
  }
  try {
    const headers: HeadersInit = {
      Authorization: `Bearer ${auth.token}`,
      "Content-Type": "application/json",
      "X-Request-ID": requestId,
    };
    const idempotencyKey = request.headers.get("Idempotency-Key");
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
    const upstream = await fetch(new URL(path, serverEnv.apiBaseUrl), {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(timeout)]),
    });
    if (upstream.status === 401 || upstream.status === 403) {
      return failure(upstream.status, "unauthorized", "登录验证失败，请重新登录。", requestId);
    }
    if (![200, 201, 204, 404, 409, 422, 503].includes(upstream.status)) {
      return failure(502, "boss_connection_unavailable", "连接服务暂不可用，请稍后读取并核对。", requestId);
    }
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store", "X-Request-ID": requestId },
    });
  } catch (error) {
    if (!(error instanceof TypeError || error instanceof DOMException)) throw error;
    return failure(502, "boss_connection_unavailable", "未能确认连接请求结果，请重新读取连接状态。", requestId);
  }
}
