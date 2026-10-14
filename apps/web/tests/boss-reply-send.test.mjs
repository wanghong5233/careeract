import assert from "node:assert/strict";
import test from "node:test";
import * as React from "react";
import { loadSource } from "./load-source.mjs";

const Button = ({ children, ...props }) => React.createElement("button", props, children);
const Container = ({ children }) => React.createElement("div", {}, children);
const reply = { id: "reply-1", version: "version-1", conversation_id: "thread-1", message_id: "m1", decision: { text: "Synthetic reply" } };
const saved = { id: "send-1", status: "unknown", text: reply.decision.text, conversation_id: reply.conversation_id, message_id: reply.message_id, evidence_message_id: null, cleanup_required: false };
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
  let props = { reply, blocked: false };
  const { BossReplySend } = loadSource("components/boss-reply-send.tsx", {
    react: { ...React,
      useState: initial => { const i = stateIndex++; if (!(i in states)) states[i] = initial; return [states[i], value => { states[i] = typeof value === "function" ? value(states[i]) : value; }]; },
      useRef: initial => refs[refIndex++] ??= { current: initial },
      useCallback: fn => fn,
      useEffect: fn => effects.push(fn),
    },
    "@/components/ui/button": { Button },
    "@/components/ui/dialog": { Dialog: Container, DialogContent: Container, DialogTitle: Container, DialogDescription: Container, DialogFooter: Container },
    "@/lib/latest-request": loadSource("lib/latest-request.ts"),
  }, { fetch });
  const render = () => { stateIndex = refIndex = 0; return BossReplySend(props); };
  const button = label => elements(render()).find(e => e.type === Button && text(e) === label);
  render();
  const cleanup = effects[0]();
  return { render, button, cleanup, setReply: value => { props = { ...props, reply: value }; } };
}
const settle = async () => { for (let i = 0; i < 5; i++) await new Promise(resolve => setImmediate(resolve)); };

test("unknown send restores without replay or new authorization", async () => {
  const calls = [];
  const fixture = panel(async (url, options) => { calls.push(options); return Response.json(saved); });
  await settle();
  assert.match(text(fixture.render()), /发送结果未知/);
  assert.equal(fixture.button("审阅并发送回复"), undefined);
  assert.ok(calls.every(options => !options.method && options.cache === "no-store"));
  fixture.cleanup();
});

test("state read failure prevents authorizing another send", async () => {
  const fixture = panel(async () => new Response(null, { status: 503 }));
  await settle();
  assert.equal(fixture.button("审阅并发送回复").props.disabled, true);
  assert.match(text(fixture.render()), /无法核对发送状态/);
  fixture.cleanup();
});

test("lost POST restores durable unknown and never retries", async () => {
  let persisted = false;
  const writes = [];
  const fixture = panel(async (url, options) => {
    if (options.method) { writes.push(options); persisted = true; throw new TypeError("response lost"); }
    return Response.json(persisted ? saved : null);
  });
  await settle();
  fixture.button("审阅并发送回复").props.onClick();
  fixture.button("授权本次发送").props.onClick();
  fixture.button("授权本次发送").props.onClick();
  await settle();
  assert.equal(writes.length, 1);
  assert.deepEqual(JSON.parse(writes[0].body), { version: "version-1", authorize_send: true });
  assert.match(text(fixture.render()), /发送结果未知/);
  assert.equal(fixture.button("审阅并发送回复"), undefined);
  fixture.cleanup();
});

test("review holds the exact version when source changes", async () => {
  const writes = [];
  const fixture = panel(async (url, options) => {
    if (options.method) { writes.push(options); return Response.json(saved); }
    return Response.json(null);
  });
  await settle();
  fixture.button("审阅并发送回复").props.onClick();
  fixture.setReply({ ...reply, version: "version-2", decision: { text: "Changed reply" } });
  assert.match(text(fixture.render()), /Synthetic reply/);
  fixture.button("授权本次发送").props.onClick();
  await settle();
  assert.equal(JSON.parse(writes[0].body).version, "version-1");
  fixture.cleanup();
});

test("queued cancellation uses the existing task and restores result", async () => {
  let cancelled = false;
  const writes = [];
  const fixture = panel(async (url, options) => {
    if (options.method) { writes.push([url, options]); cancelled = true; }
    return Response.json({ ...saved, status: cancelled ? "cancelled" : "accepted" });
  });
  await settle();
  fixture.button("撤销未开始的发送").props.onClick();
  await settle();
  assert.equal(writes.length, 1);
  assert.equal(writes[0][1].method, "DELETE");
  assert.match(text(fixture.render()), /已取消/);
  fixture.cleanup();
});

test("late state read cannot update an unmounted send panel", async () => {
  let finish;
  const fixture = panel(async () => new Promise(resolve => { finish = resolve; }));
  fixture.cleanup();
  finish(Response.json(saved));
  await settle();
  assert.doesNotMatch(text(fixture.render()), /发送结果未知/);
  assert.equal(fixture.button("审阅并发送回复").props.disabled, true);
});
