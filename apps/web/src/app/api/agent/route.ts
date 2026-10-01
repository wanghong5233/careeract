import { NextRequest, NextResponse } from "next/server";

import { getAuth } from "@/lib/auth";
import { serverEnv } from "@/lib/server-env";

function failure(status: number, code: string, message: string, requestId: string) {
  return NextResponse.json(
    { error: { code, message, request_id: requestId } },
    { status, headers: { "Cache-Control": "no-store", "X-Request-ID": requestId } },
  );
}

async function readBody(request: NextRequest, requestId: string): Promise<Uint8Array | Response> {
  if (request.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase() !== "application/json" ||
      ![null, "identity"].includes(request.headers.get("content-encoding"))) {
    return failure(415, "unsupported_content", "当前仅接收 JSON 文本。", requestId);
  }
  const reader = request.body?.getReader();
  if (!reader) return failure(400, "missing_body", "缺少委托内容。", requestId);
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 262_144) {
        await reader.cancel();
        return failure(413, "content_too_large", "内容过大，请精简后重试。", requestId);
      }
      chunks.push(value);
    }
    return Buffer.concat(chunks);
  } catch (error) {
    if (!(error instanceof TypeError || error instanceof DOMException)) throw error;
    return failure(400, "invalid_body", "未能读取委托内容，请检查连接。", requestId);
  } finally {
    reader.releaseLock();
  }
}

export async function POST(request: NextRequest): Promise<Response> {
  const requestId = crypto.randomUUID();
  if (request.headers.get("origin") !== new URL(serverEnv.betterAuthUrl).origin) {
    return failure(403, "forbidden", "请求来源无效，请从工作台发送。", requestId);
  }

  const auth = getAuth();
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session) {
    return failure(401, "unauthorized", "登录已失效，请重新登录。", requestId);
  }

  const { token } = await auth.api.getToken({ headers: request.headers });
  const body = await readBody(request, requestId);
  if (body instanceof Response) return body;
  let upstream: Response;
  try {
    upstream = await fetch(new URL("/agui", serverEnv.apiBaseUrl), {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        "X-Request-ID": requestId,
      },
      body: Buffer.from(body),
      cache: "no-store",
      redirect: "error",
      signal: request.signal,
    });
  } catch (error: unknown) {
    if (!(error instanceof TypeError || error instanceof DOMException)) throw error;
    if (request.signal.aborted) {
      return new Response(null, { status: 499 });
    }
    console.error("Agent upstream request failed", { requestId });
    return failure(502, "agent_unavailable", "伙伴暂时无法回应，请稍后重试。", requestId);
  }

  const responseHeaders = new Headers();
  responseHeaders.set(
    "Content-Type",
    upstream.headers.get("content-type") ?? "text/event-stream",
  );
  responseHeaders.set("Cache-Control", "no-store");
  responseHeaders.set("X-Request-ID", requestId);

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}
