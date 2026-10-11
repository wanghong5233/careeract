import assert from "node:assert/strict";
import test from "node:test";
import * as React from "react";
import { loadSource } from "./load-source.mjs";

function elements(value) {
  if (Array.isArray(value)) return value.flatMap(elements);
  if (!React.isValidElement(value)) return [];
  return [value, ...elements(value.props.children)];
}

function scene(allowLoginControl = false) {
  const states = [], refs = [], effects = [], timers = new Map();
  let stateIndex = 0, refIndex = 0, listener;
  const Button = props => React.createElement("button", props);
  const Icon = () => null;
  const window = {
    location: { origin: "https://careeract.example" },
    addEventListener: (_name, callback) => { listener = callback; },
    removeEventListener: (_name, callback) => { if (listener === callback) listener = null; },
  };
  const { BrowserScene } = loadSource("components/browser-scene.tsx", {
    react: {
      ...React,
      useState: initial => {
        const index = stateIndex++;
        if (!(index in states)) states[index] = initial;
        return [states[index], value => { states[index] = typeof value === "function" ? value(states[index]) : value; }];
      },
      useRef: initial => refs[refIndex++] ??= { current: initial },
      useEffect: callback => effects.push(callback),
    },
    "lucide-react": { ChevronDown: Icon, ChevronUp: Icon, Maximize2: Icon, Minimize2: Icon, RefreshCw: Icon },
    "@/components/ui/button": { Button },
  }, {
    window,
    setTimeout: callback => { const id = timers.size + 1; timers.set(id, callback); return id; },
    clearTimeout: id => timers.delete(id),
  });
  const render = () => { stateIndex = 0; refIndex = 0; return BrowserScene({ sessionId: "session-a", allowLoginControl }); };
  const frameWindow = {};
  const iframe = elements(render()).find(element => element.type === "iframe");
  iframe.props.ref.current = { contentWindow: frameWindow };
  const cleanup = effects[0]();
  const send = (overrides = {}) => listener({
    origin: window.location.origin,
    source: frameWindow,
    data: { source: "careeract-browser-viewer", sessionId: "session-a", mode: "watch", status: "connected" },
    ...overrides,
  });
  return { render, send, cleanup, timers, status: () => states[2] };
}

test("viewer accepts status only from its own frame and does not reset on iframe load", () => {
  const fixture = scene();
  fixture.send({ source: {} });
  fixture.send({ origin: "https://foreign.example" });
  fixture.send({ data: { source: "careeract-browser-viewer", sessionId: "other", mode: "watch", status: "connected" } });
  assert.equal(fixture.status(), "loading");
  fixture.send();
  assert.equal(fixture.status(), "connected");
  const iframe = elements(fixture.render()).find(element => element.type === "iframe");
  iframe.props.onLoad?.();
  fixture.timers.values().next().value();
  assert.equal(fixture.status(), "connected");
  fixture.cleanup();
  assert.equal(fixture.timers.size, 0);
});

test("viewer missing its handshake stops loading and offers an explicit reconnection", () => {
  const fixture = scene();
  fixture.timers.values().next().value();
  assert.equal(fixture.status(), "error");
  const before = elements(fixture.render()).find(element => element.type === "iframe").key;
  const reconnect = elements(fixture.render()).find(element => element.props["aria-label"] === "重新连接浏览器现场");
  assert.ok(reconnect);
  reconnect.props.onClick();
  assert.equal(fixture.status(), "loading");
  assert.notEqual(elements(fixture.render()).find(element => element.type === "iframe").key, before);
  fixture.cleanup();
});

test("human login explicitly replaces the watch connection and returns to watch, with no control on read-only tasks", () => {
  const readonly = scene();
  assert.equal(elements(readonly.render()).some(element => element.props.children === "操作登录浏览器"), false);
  readonly.cleanup();
  const login = scene(true);
  const button = label => elements(login.render()).find(element => element.props.children === label);
  const frame = () => elements(login.render()).find(element => element.type === "iframe");
  assert.ok(frame().props.src.endsWith("mode=watch"));
  const watching = frame().key;
  button("操作登录浏览器").props.onClick();
  assert.ok(frame().props.src.endsWith("mode=control"));
  assert.notEqual(frame().key, watching);
  assert.equal(frame().props.title, "人工登录浏览器");
  button("返回观看").props.onClick();
  assert.ok(frame().props.src.endsWith("mode=watch"));
  login.cleanup();
});
