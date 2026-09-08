import { toNextJsHandler } from "better-auth/next-js";

import { getAuth } from "@/lib/auth";

export function GET(request: Request): Response | Promise<Response> {
  return toNextJsHandler(getAuth()).GET(request);
}

export function POST(request: Request): Response | Promise<Response> {
  return toNextJsHandler(getAuth()).POST(request);
}
