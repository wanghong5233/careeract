import assert from "node:assert/strict";
import test from "node:test";
import * as React from "react";
import { loadSource } from "./load-source.mjs";

const Button = ({ children, ...props }) => React.createElement("button", props, children);
const Container = ({ children }) => React.createElement("div", {}, children);
const connectionId = "d1965402-3575-4125-b339-6e489e5a3209";
const source = { readTaskId: "read-1", conversationId: "thread-1", messageId: "m1", content: "Synthetic message" };
const saved = { id: "reply-1", ...source, conversation_id: "thread-1", message_id: "m1", version: "version-1", status: "waiting", created_at: new Date().toISOString(), decision: { category: "routine", text: "Synthetic reply", reason: "Confirmed facts", facts: [] } };
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
  let props = { connectionId, source, blocked: false };
  const { BossReplies } = loadSource("components/boss-replies.tsx", {
    react: { ...React,
      useState: initial => { const i = stateIndex++; if (!(i in states)) states[i] = initial; return [states[i], value => { states[i] = typeof value === "function" ? value(states[i]) : value; }]; },
      useRef: initial => refs[refIndex++] ??= { current: initial },
      useCallback: fn => fn,
      useEffect: fn => effects.push(fn),
    },
    "@/components/ui/button": { Button },
    "@/components/boss-reply-send": { BossReplySend: Container },
    "@/components/ui/dialog": { Dialog: Container, DialogContent: Container, DialogTitle: Container, DialogDescription: Container, DialogFooter: Container },
    "@/lib/latest-request": loadSource("lib/latest-request.ts"),
  }, { fetch });
  const render = () => { stateIndex = refIndex = 0; return BossReplies(props); };
  const button = label => elements(render()).find(e => e.type === Button && text(e) === label);
  render();
  const cleanup = effects[0]();
  return { render, button, cleanup, setSource: value => { props = { ...props, source: value }; } };
}
const settle = async () => { for (let i = 0; i < 5; i++) await new Promise(resolve => setImmediate(resolve)); };

test("saved decision restores without submitting or dispatching again", async () => {
  const calls = [];
  const fixture = panel(async (url, options) => { calls.push([url, options]); return Response.json({ items: [saved], next_cursor: null }); });
  await settle();
  assert.match(text(fixture.render()), /Synthetic reply/);
  assert.equal(fixture.button("生成回复建议").props.disabled, true);
  assert.ok(calls.every(([, options]) => options.cache === "no-store" && !options.method));
  fixture.cleanup();
});

test("historical acknowledgement remains readable without a send action", async () => {
  const fixture = panel(async () => Response.json({
    items: [{ ...saved, decision: { ...saved.decision, category: "acknowledgement" } }],
    next_cursor: null,
  }));
  await settle();
  const view = fixture.render();
  assert.match(text(view), /旧建议已停用/);
  assert.match(text(view), /Synthetic reply/);
  assert.equal(elements(view).some(element => element.props.reply), false);
  fixture.cleanup();
});

test("lost create response restores durable job without replaying POST", async () => {
  let persisted = false;
  const writes = [];
  const fixture = panel(async (url, options) => {
    if (options.method) { writes.push(options); persisted = true; throw new TypeError("network response lost"); }
    return Response.json({ items: persisted ? [saved] : [], next_cursor: null });
  });
  await settle();
  fixture.button("生成回复建议").props.onClick();
  fixture.button("生成并保存建议").props.onClick();
  await settle();
  assert.equal(writes.length, 1);
  assert.equal(JSON.parse(writes[0].body).disclose_to_model, true);
  assert.ok(writes[0].headers["Idempotency-Key"]);
  assert.match(text(fixture.render()), /Synthetic reply/);
  assert.equal(fixture.button("生成回复建议").props.disabled, true);
  fixture.cleanup();
});

test("disclosure binds reviewed source even when selected conversation changes", async () => {
  const writes = [];
  const fixture = panel(async (url, options) => {
    if (options.method) { writes.push(JSON.parse(options.body)); return Response.json(saved); }
    return Response.json({ items: [], next_cursor: null });
  });
  await settle();
  fixture.button("生成回复建议").props.onClick();
  fixture.setSource({ ...source, conversationId: "thread-2", messageId: "m2" });
  fixture.button("生成并保存建议").props.onClick();
  await settle();
  assert.equal(writes[0].conversation_id, "thread-1");
  assert.equal(writes[0].message_id, "m1");
  fixture.cleanup();
});

test("cancel uses restored version and prevents concurrent writes", async () => {
  const writes = [];
  let resolveWrite;
  const fixture = panel(async (url, options) => {
    if (options.method) { writes.push(options); return new Promise(resolve => { resolveWrite = resolve; }); }
    return Response.json({ items: [{ ...saved, status: "running" }], next_cursor: null });
  });
  await settle();
  const stop = fixture.button("停止此任务");
  stop.props.onClick(); stop.props.onClick();
  assert.equal(writes.length, 1);
  assert.equal(writes[0].method, "DELETE");
  assert.deepEqual(JSON.parse(writes[0].body), { version: saved.version });
  resolveWrite(Response.json({ ...saved, status: "cancelled" }));
  await settle();
  fixture.cleanup();
});

test("unmounted read response cannot replace current view", async () => {
  let resolveRead;
  const fixture = panel(async () => new Promise(resolve => { resolveRead = resolve; }));
  fixture.cleanup();
  resolveRead(Response.json({ items: [saved], next_cursor: null }));
  await settle();
  assert.doesNotMatch(text(fixture.render()), /Synthetic reply/);
});
