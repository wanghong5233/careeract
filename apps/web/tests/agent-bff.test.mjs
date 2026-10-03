import assert from "node:assert/strict";
import test from "node:test";
import { loadSource } from "./load-source.mjs";

const origin = "https://careeract.example";
const projectId = "14c9947b-49cf-4ea3-8eaf-bbe2ea5d13f3";

function fixture(route, { session = { user: { id: "owner" } }, token = "test-token", upstream = () => Response.json({ items: [] }) } = {}) {
  const calls = [];
  const handler = loadSource(`app/api/agent/${route}/route.ts`, {
    "next/server": { NextResponse: { json: Response.json } },
    "@/lib/auth": { getAuth: () => ({ api: { getSession: async () => session, getToken: async () => ({ token }) } }) },
    "@/lib/agent-session": { agentThreadId: owner => `session-${owner}` },
    "@/lib/server-env": { serverEnv: { betterAuthUrl: origin, apiBaseUrl: "https://api.example" } },
  }, { fetch: async (url, options) => { calls.push({ url, options }); return upstream(); } });
  return { handler, calls };
}

function sessionRequest(body = { project_id: projectId }, headers = {}) {
  return new Request(`${origin}/api/agent/session`, {
    method: "PUT", headers: { Origin: origin, "Content-Type": "application/json", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

test("history GET reads the server-derived session without writing its project association", async () => {
  const { handler, calls } = fixture("history");
  const response = await handler.GET(new Request(`${origin}/api/agent/history?session_id=another-user`));
  assert.equal(response.status, 200);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.method ?? "GET", "GET");
  assert.equal(calls[0].url.searchParams.get("session_id"), "session-owner");
  assert.equal(calls[0].options.cache, "no-store");
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("history preserves missing session status", async () => {
  const { handler } = fixture("history", { upstream: () => Response.json({ error: "not_found" }, { status: 404 }) });
  assert.equal((await handler.GET(new Request(`${origin}/api/agent/history`))).status, 404);
});

for (const route of ["session", "history"]) {
  for (const identity of [{ session: null }, { token: null }]) {
    test(`${route} rejects missing ${identity.session === null ? "session" : "token"} before forwarding`, async () => {
      const { handler, calls } = fixture(route, identity);
      const response = route === "session" ? await handler.PUT(sessionRequest()) : await handler.GET(new Request(`${origin}/api/agent/history`));
      assert.equal(response.status, 401);
      assert.equal(calls.length, 0);
    });
  }
  test(`${route} sanitizes upstream auth errors and hides internal failures`, async () => {
    for (const status of [401, 403, 500]) {
      const { handler } = fixture(route, { upstream: () => new Response("private upstream diagnostics", { status }) });
      const response = route === "session" ? await handler.PUT(sessionRequest()) : await handler.GET(new Request(`${origin}/api/agent/history`));
      assert.equal(response.status, status === 500 ? 502 : status);
      assert.ok(!(await response.text()).includes("private upstream"));
    }
  });
  test(`${route} reports network failures but does not swallow programming errors`, async () => {
    for (const failure of [new TypeError("private network details"), new Error("programming failure")]) {
      const { handler } = fixture(route, { upstream: () => { throw failure; } });
      const invoke = () => route === "session" ? handler.PUT(sessionRequest()) : handler.GET(new Request(`${origin}/api/agent/history`));
      if (failure instanceof TypeError) {
        const response = await invoke();
        assert.equal(response.status, 502);
        assert.ok(!(await response.text()).includes("private network"));
      } else await assert.rejects(invoke, failure);
    }
  });
}

test("session rejects cross-origin and malformed input without upstream writes", async () => {
  const cases = [
    [sessionRequest({}, { Origin: "https://other.example" }), 403],
    [sessionRequest({}, { "Content-Type": "text/plain" }), 415],
    [sessionRequest("{"), 400],
    [sessionRequest("x".repeat(4097)), 413],
    [sessionRequest([]), 422],
    [sessionRequest(null), 422],
    [sessionRequest({ user_id: "other", project_id: projectId }), 422],
    [sessionRequest({ project_id: "not-a-uuid" }), 422],
    [sessionRequest({ project_id: 42 }), 422],
  ];
  for (const [request, status] of cases) {
    const { handler, calls } = fixture("session");
    assert.equal((await handler.PUT(request)).status, status);
    assert.equal(calls.length, 0);
  }
});

test("session derives identity from authentication and preserves explicit detach", async () => {
  for (const body of [{ project_id: projectId }, { project_id: null }, {}]) {
    const { handler, calls } = fixture("session");
    assert.equal((await handler.PUT(sessionRequest(body))).status, 200);
    assert.deepEqual(JSON.parse(calls[0].options.body), { session_id: "session-owner", project_id: body.project_id ?? null });
    assert.equal(calls[0].options.redirect, "error");
    assert.equal(calls[0].options.cache, "no-store");
  }
});
