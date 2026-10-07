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

test("connection card reads, records and revokes exact version without suggesting browser login", async () => {
  const calls = [];
  const fixture = card(async (url, options = {}) => {
    calls.push({ url, options });
    return Response.json(options.method === "POST" ? { id: connectionId, version: "v1", status: "pending" }
      : options.method === "DELETE" ? { id: connectionId, version: "v2", status: "revoked" } : null);
  });
  fixture.mount();
  await settle();
  assert.match(text(fixture.render()), /尚未连接/);
  assert.match(text(fixture.render()), /登录入口尚未开放/);
  assert.match(text(fixture.render()), /密码、短信验证码和验证码/);
  fixture.click("记录连接请求");
  await settle();
  assert.match(text(fixture.render()), /连接请求已记录/);
  assert.ok(calls[1].options.headers["Idempotency-Key"]);
  fixture.click("撤销连接请求");
  await settle();
  assert.match(text(fixture.render()), /请求已撤销/);
  assert.equal(calls[2].url, `/api/connections/boss/${connectionId}`);
  assert.deepEqual(JSON.parse(calls[2].options.body), { version: "v1" });
});

test("uncertain start requires reading before another write and keeps the same request key", async () => {
  const calls = [];
  const fixture = card(async (url, options = {}) => {
    calls.push({ url, options });
    if (options.method) throw new TypeError("Synthetic connection lost");
    return Response.json(null);
  });
  fixture.mount();
  await settle();
  fixture.click("记录连接请求");
  await settle();
  assert.match(text(fixture.render()), /未能确认请求结果/);
  const write = elements(fixture.render()).find(item => item.type === Placeholder && text(item).includes("记录连接请求"));
  assert.equal(write.props.disabled, true);
  assert.equal(calls.length, 2);
  fixture.click("重新读取");
  await settle();
  fixture.click("记录连接请求");
  await settle();
  assert.equal(calls[1].options.headers["Idempotency-Key"], calls[3].options.headers["Idempotency-Key"]);
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
