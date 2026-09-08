import { NextRequest, NextResponse } from "next/server";

import { getAuth } from "@/lib/auth";
import { serverEnv } from "@/lib/server-env";

export async function POST(request: NextRequest): Promise<Response> {
  if (request.headers.get("origin") !== new URL(serverEnv.betterAuthUrl).origin) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  const auth = getAuth();
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { token } = await auth.api.getToken({ headers: request.headers });
  const requestId = crypto.randomUUID();
  let upstream: Response;
  try {
    upstream = await fetch(new URL("/agui", serverEnv.apiBaseUrl), {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        Authorization: `Bearer ${token}`,
        "Content-Type": request.headers.get("content-type") ?? "application/json",
        "X-Request-ID": requestId,
      },
      body: await request.arrayBuffer(),
      cache: "no-store",
      signal: request.signal,
    });
  } catch (error: unknown) {
    if (request.signal.aborted) {
      return new Response(null, { status: 499 });
    }
    console.error(
      "Agent upstream request failed",
      error instanceof Error ? error.message : "unknown error",
    );
    return NextResponse.json(
      { error: "Agent service unavailable", requestId },
      { status: 502 },
    );
  }

  const responseHeaders = new Headers();
  responseHeaders.set(
    "Content-Type",
    upstream.headers.get("content-type") ?? "text/event-stream",
  );
  responseHeaders.set("Cache-Control", "no-cache");
  responseHeaders.set("X-Request-ID", requestId);

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}
