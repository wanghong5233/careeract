import assert from "node:assert/strict";
import test from "node:test";
import * as React from "react";
import { loadSource } from "./load-source.mjs";

const Placeholder = ({ children, ...props }) => React.createElement("button", props, children);
const origin = "https://careeract.example";
const connectionId = "d1965402-3575-4125-b339-6e489e5a3209";

function elements(value) {
  if (Array.isArray(value)) return value.flatMap(elements);
  if (!React.isValidElement(value)) return [];
  return [value, ...elements(value.props.children)];
}

function text(value) {
  if (Array.isArray(value)) return value.map(text).join(" ");
  if (React.isValidElement(value)) return text(value.props.children);
  return typeof value === "string" ? value : "";
}

function card(fetch) {
  const states = [], refs = [], effects = [];
  let stateIndex = 0, refIndex = 0;
  const { BossConnectionCard } = loadSource("components/boss-connection-card.tsx", {
    react: {
      ...React,
      useState: initial => {
        const index = stateIndex++;
        if (!(index in states)) states[index] = initial;
        return [states[index], value => { states[index] = value; }];
      },
      useRef: initial => refs[refIndex++] ??= { current: initial },
      useCallback: callback => callback,
      useEffect: callback => { if (!effects.length) effects.push(callback); },
    },
    "lucide-react": { LoaderCircle: Placeholder, RefreshCw: Placeholder },
    "@/components/ui/button": { Button: Placeholder },
    "@/lib/latest-request": loadSource("lib/latest-request.ts"),
    "@/lib/utils": { cn: (...values) => values.filter(Boolean).join(" ") },
  }, { fetch });
  const render = () => { stateIndex = 0; refIndex = 0; return BossConnectionCard(); };
  const click = label => {
    const element = elements(render()).find(item => item.type === Placeholder && text(item).includes(label));
    assert.ok(element, label);
    assert.equal(element.props.disabled, false, label);
    element.props.onClick();
  };
  render();
  return { render, click, mount: () => effects[0](), states };
}

const settle = () => new Promise(resolve => setImmediate(resolve));

test("connection card starts and stops an explicitly authorized browser login", async () => {
  const calls = [];
  const fixture = card(async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/login") && options.method === "POST") return Response.json({ attempt_status: "waiting", outcome: "browser_created", browser_session_id: connectionId });
    if (url.endsWith("/login") && options.method === "DELETE") return Response.json({ attempt_status: "cancelled", outcome: "browser_released", browser_session_id: connectionId });
    if (url.endsWith("/login")) return Response.json(null);
    return Response.json({ id: connectionId, version: "v1", status: "pending" });
  });
  fixture.mount();
  await settle();
  assert.match(text(fixture.render()), /连接请求已记录/);
  assert.match(text(fixture.render()), /密码、短信验证码和验证码/);
  fixture.click("开始安全登录");
  await settle();
  assert.match(text(fixture.render()), /打开安全浏览器/);
  assert.deepEqual(JSON.parse(calls[2].options.body), { version: "v1", authorize_login: true });
  assert.ok(calls[2].options.headers["Idempotency-Key"]);
  fixture.click("停止登录");
  await settle();
  assert.match(text(fixture.render()), /开始安全登录/);
  assert.deepEqual(JSON.parse(calls[4].options.body), { version: "v1" });
});

test("uncertain start requires reading before another write and keeps the same request key", async () => {
  const calls = [];
  const fixture = card(async (url, options = {}) => {
    calls.push({ url, options });
    if (options.method) throw new TypeError("Synthetic connection lost");
    if (!options.method && url.endsWith("/login")) return Response.json(null);
    return Response.json({ id: connectionId, version: "v1", status: "pending" });
  });
  fixture.mount();
  await settle();
  fixture.click("开始安全登录");
  await settle();
  assert.match(text(fixture.render()), /未能确认登录请求结果/);
  const write = elements(fixture.render()).find(item => item.type === Placeholder && text(item).includes("开始安全登录"));
  assert.equal(write.props.disabled, true);
  assert.equal(calls.length, 3);
  fixture.click("重新读取");
  await settle();
  fixture.click("开始安全登录");
  await settle();
  assert.equal(calls[2].options.headers["Idempotency-Key"], calls[5].options.headers["Idempotency-Key"]);
});

test("unmounted read cannot update connection state", async () => {
  let resolve;
  const fixture = card(() => new Promise(callback => { resolve = callback; }));
  const cleanup = fixture.mount();
  const before = [...fixture.states];
  cleanup();
  resolve(Response.json({ id: connectionId, version: "v1", status: "pending" }));
  await settle();
  assert.deepEqual(fixture.states, before);
});

function bff({ authorized = true, upstream = () => Response.json(null) } = {}) {
  const calls = [];
  const shared = {
    authenticate: async () => authorized ? { token: "synthetic-token" } : { response: Response.json({}, { status: 401 }) },
    hasTrustedOrigin: request => request.headers.get("Origin") === origin,
    failure: (status, code, message) => Response.json({ error: { code, message } }, { status }),
    validProjectId: value => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value),
  };
  const helper = loadSource("app/api/connections/boss/_helpers.ts", {
    "next/server": { NextResponse: Response },
    "@/app/api/projects/_helpers": shared,
    "@/lib/server-env": { serverEnv: { apiBaseUrl: "https://api.example" } },
  }, { fetch: async (url, options) => { calls.push({ url, options }); return upstream(); } });
  return {
    calls,
    root: loadSource("app/api/connections/boss/route.ts", { "./_helpers": helper }),
    detail: loadSource("app/api/connections/boss/[connectionId]/route.ts", { "../_helpers": helper, "@/app/api/projects/_helpers": shared }),
    login: loadSource("app/api/connections/boss/[connectionId]/login/route.ts", { "../../_helpers": helper, "@/app/api/projects/_helpers": shared }),
    viewer: loadSource("app/api/browser/sessions/[sessionId]/viewer/route.ts", {
      "@/app/api/projects/_helpers": shared,
      "@/lib/server-env": { serverEnv: { apiBaseUrl: "https://api.example" } },
    }, { fetch: async (url, options) => { calls.push({ url, options }); return upstream(); } }),
  };
}

const request = (method, body = {}, headers = {}) => new Request(`${origin}/api/connections/boss`, {
  method, headers: { Origin: origin, "Content-Type": "application/json", "Idempotency-Key": connectionId, ...headers },
  ...(method === "GET" ? {} : { body: JSON.stringify(body) }),
});

test("BFF protects origin and identity, limits body, preserves key and revoke version", async () => {
  const denied = bff({ authorized: false });
  assert.equal((await denied.root.GET(request("GET"))).status, 401);
  assert.equal(denied.calls.length, 0);
  const fixture = bff({ upstream: () => Response.json({ status: "pending" }, { status: 201 }) });
  assert.equal((await fixture.root.POST(request("POST", {}, { Origin: "https://other.example" }))).status, 403);
  assert.equal((await fixture.root.POST(request("POST", {}, { "Content-Type": "text/plain" }))).status, 415);
  assert.equal((await fixture.root.POST(request("POST", "x".repeat(1025)))).status, 413);
  assert.equal(fixture.calls.length, 0);
  const response = await fixture.root.POST(request("POST"));
  assert.equal(response.status, 201);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(fixture.calls[0].options.headers["Idempotency-Key"], connectionId);
  assert.equal(fixture.calls[0].options.headers.Authorization, "Bearer synthetic-token");
  assert.equal(fixture.calls[0].options.redirect, "error");
  await fixture.detail.DELETE(request("DELETE", { version: "v1" }), { params: Promise.resolve({ connectionId }) });
  assert.equal(new URL(fixture.calls[1].url).pathname, `/api/v1/connections/boss/${connectionId}`);
  assert.deepEqual(JSON.parse(fixture.calls[1].options.body), { version: "v1" });
});

test("BFF reports unavailable or uncertain results once and never retries", async () => {
  for (const upstream of [() => { throw new TypeError("Private network details"); }, () => new Response("Private diagnostics", { status: 500 })]) {
    const fixture = bff({ upstream });
    const response = await fixture.root.POST(request("POST"));
    assert.equal(response.status, 502);
    assert.equal(fixture.calls.length, 1);
    assert.ok(!(await response.text()).includes("Private"));
  }
});

test("login BFF keeps explicit authorization, key, version and long-operation timeout", async () => {
  const fixture = bff({ upstream: () => Response.json({ attempt_status: "waiting" }) });
  const context = { params: Promise.resolve({ connectionId }) };
  const body = { version: "v1", authorize_login: true };
  assert.equal((await fixture.login.POST(request("POST", body, { Origin: "https://other.example" }), context)).status, 403);
  assert.equal((await fixture.login.GET(request("GET"), { params: Promise.resolve({ connectionId: "../other" }) })).status, 422);
  assert.equal(fixture.calls.length, 0);
  assert.equal((await fixture.login.POST(request("POST", body), context)).status, 200);
  assert.equal(new URL(fixture.calls[0].url).pathname, `/api/v1/connections/boss/${connectionId}/login`);
  assert.deepEqual(JSON.parse(fixture.calls[0].options.body), body);
  assert.equal(fixture.calls[0].options.headers["Idempotency-Key"], connectionId);
  assert.equal(fixture.calls[0].options.headers.Authorization, "Bearer synthetic-token");
  await fixture.login.GET(request("GET"), context);
  await fixture.login.DELETE(request("DELETE", { version: "v2" }), context);
  assert.equal(fixture.calls[1].options.method, "GET");
  assert.equal(fixture.calls[2].options.method, "DELETE");
  assert.deepEqual(JSON.parse(fixture.calls[2].options.body), { version: "v2" });
  const denied = bff({ authorized: false });
  assert.equal((await denied.login.POST(request("POST", body), context)).status, 401);
  assert.equal(denied.calls.length, 0);
  const lost = bff({ upstream: () => { throw new TypeError("Private lifecycle diagnostics"); } });
  assert.equal((await lost.login.POST(request("POST", body), context)).status, 502);
  assert.equal(lost.calls.length, 1);
});

test("viewer BFF keeps HTML same-origin and forwards the short-lived cookie", async () => {
  const fixture = bff({ upstream: () => new Response("<html>viewer</html>", { status: 200, headers: { "content-type": "text/html", "set-cookie": "careeract_viewer=redacted; HttpOnly" } }) });
  const context = { params: Promise.resolve({ sessionId: connectionId }) };
  const viewerRequest = new Request(`${origin}/api/browser/sessions/${connectionId}/viewer?pageId=page-a`);
  Object.defineProperty(viewerRequest, "nextUrl", { value: new URL(viewerRequest.url) });
  const response = await fixture.viewer.GET(viewerRequest, context);
  assert.equal(response.status, 200);
  assert.equal(await response.text(), "<html>viewer</html>");
  assert.equal(response.headers.get("set-cookie"), "careeract_viewer=redacted; HttpOnly");
  assert.equal(new URL(fixture.calls[0].url).pathname, `/api/v1/browser/sessions/${connectionId}/viewer`);
  assert.equal(new URL(fixture.calls[0].url).searchParams.get("pageId"), "page-a");
});
