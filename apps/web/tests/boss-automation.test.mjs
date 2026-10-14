import assert from "node:assert/strict";
import test from "node:test";
import * as React from "react";
import { loadSource } from "./load-source.mjs";

const Button = ({ children, ...props }) => React.createElement("button", props, children);
const Container = ({ children }) => React.createElement("div", {}, children);
const saved = { id: "a1", version: "v1", status: "running", conversation_ids: ["thread-1"], max_sends: 5, sends_reserved: 1, expires_at: "2099-01-01T00:00:00Z", outcome: null };
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
function panel(fetch) {
  const states = [], refs = [], effects = [];
  let stateIndex = 0, refIndex = 0;
  const { BossAutomation } = loadSource("components/boss-automation.tsx", {
    react: { ...React,
      useState: initial => { const i = stateIndex++; if (!(i in states)) states[i] = initial; return [states[i], value => { states[i] = typeof value === "function" ? value(states[i]) : value; }]; },
      useRef: initial => refs[refIndex++] ??= { current: initial },
      useCallback: fn => fn, useEffect: fn => effects.push(fn),
    },
    "@/components/ui/button": { Button },
    "@/components/ui/dialog": { Dialog: Container, DialogContent: Container, DialogTitle: Container, DialogDescription: Container, DialogFooter: Container },
    "@/lib/latest-request": loadSource("lib/latest-request.ts"),
  }, { fetch });
  const props = { connectionId: "c1", version: "connection-v1", blocked: false, conversations: [{ conversation_id: "thread-1", recruiter_name: "Synthetic", company: null }], onActiveChange: () => {} };
  const render = () => { stateIndex = refIndex = 0; return BossAutomation(props); };
  const button = label => elements(render()).find(e => e.type === Button && text(e) === label);
  render();
  const cleanup = effects[0]();
  return { render, button, cleanup };
}
const settle = async () => { for (let i = 0; i < 5; i++) await new Promise(resolve => setImmediate(resolve)); };

test("running delegation restores without sending or granting new permission", async () => {
  const calls = [];
  const fixture = panel(async (url, options) => { calls.push(options); return Response.json(saved); });
  await settle();
  assert.match(text(fixture.render()), /自动回复运行中/);
  assert.equal(fixture.button("设置自动回复"), undefined);
  assert.equal(fixture.button("停止自动回复").props.disabled, false);
  assert.ok(calls.every(options => !options.method));
  fixture.cleanup();
});

test("failed restoration prevents new authorization", async () => {
  const fixture = panel(async () => new Response(null, { status: 503 }));
  await settle();
  assert.equal(fixture.button("设置自动回复").props.disabled, true);
  assert.match(text(fixture.render()), /无法读取自动回复状态/);
  fixture.cleanup();
});

test("lost start response restores saved scope and does not retry", async () => {
  let persisted = false;
  const writes = [];
  const fixture = panel(async (url, options) => {
    if (options.method) { writes.push(options); persisted = true; throw new TypeError("lost response"); }
    return Response.json(persisted ? saved : null);
  });
  await settle();
  fixture.button("设置自动回复").props.onClick();
  const checkbox = elements(fixture.render()).find(e => e.type === "input");
  checkbox.props.onChange({ target: { checked: true } });
  fixture.button("授权并启动自动回复").props.onClick();
  fixture.button("授权并启动自动回复").props.onClick();
  await settle();
  assert.equal(writes.length, 1);
  assert.deepEqual(JSON.parse(writes[0].body), { connection_id: "c1", version: "connection-v1", conversation_ids: ["thread-1"], max_sends: 5, duration_minutes: 60, interval_seconds: 300, authorize_replies: true, disclose_to_model: true });
  assert.match(text(fixture.render()), /自动回复运行中/);
  fixture.cleanup();
});

test("stop addresses saved delegation version and restores cancellation", async () => {
  let stopped = false;
  const writes = [];
  const fixture = panel(async (url, options) => {
    if (options.method) { writes.push({ url, ...options }); stopped = true; }
    return Response.json({ ...saved, status: stopped ? "cancelled" : "waiting", outcome: stopped ? "stopped" : "resume_request" });
  });
  await settle();
  assert.match(text(fixture.render()), /招聘方请求简历/);
  fixture.button("停止自动回复").props.onClick();
  await settle();
  assert.equal(writes.length, 1);
  assert.equal(writes[0].method, "DELETE");
  assert.equal(writes[0].url, "/api/recruiting/automations/a1");
  assert.deepEqual(JSON.parse(writes[0].body), { version: "v1" });
  assert.match(text(fixture.render()), /已停止/);
  fixture.cleanup();
});

test("late restoration cannot change unmounted delegation panel", async () => {
  let resolve;
  const fixture = panel(() => new Promise(done => { resolve = done; }));
  fixture.cleanup();
  resolve(Response.json(saved));
  await settle();
  assert.doesNotMatch(text(fixture.render()), /自动回复运行中/);
});
