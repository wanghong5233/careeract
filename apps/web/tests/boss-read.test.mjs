import assert from "node:assert/strict";
import test from "node:test";
import * as React from "react";
import { loadSource } from "./load-source.mjs";

const connectionId = "d1965402-3575-4125-b339-6e489e5a3209";
const taskId = "a1965402-3575-4125-b339-6e489e5a3209";
const Button = ({ children, ...props }) => React.createElement("button", props, children);
const Container = ({ children }) => React.createElement("div", {}, children);

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

function taskCard(fetch, blocked = false) {
  const states = [], refs = [], effects = [];
  let stateIndex = 0, refIndex = 0;
  const { BossReadTask } = loadSource("components/boss-read-task.tsx", {
    react: {
      ...React,
      useState: initial => {
        const index = stateIndex++;
        if (!(index in states)) states[index] = initial;
        return [states[index], value => { states[index] = typeof value === "function" ? value(states[index]) : value; }];
      },
      useRef: initial => refs[refIndex++] ??= { current: initial },
      useCallback: callback => callback,
      useEffect: callback => effects.push(callback),
    },
    "lucide-react": { LoaderCircle: Container, RefreshCw: Container },
    "@/components/browser-scene": { BrowserScene: Container },
    "@/components/ui/button": { Button },
    "@/components/ui/dialog": {
      Dialog: ({ open, children }) => open ? children : null,
      DialogContent: Container, DialogDescription: Container, DialogFooter: Container, DialogTitle: Container,
    },
    "@/lib/latest-request": loadSource("lib/latest-request.ts"),
  }, { fetch });
  const render = () => { stateIndex = 0; refIndex = 0; return BossReadTask({ connectionId, version: "v1", blocked }); };
  render();
  const cleanup = effects[0]();
  const button = label => elements(render()).find(element => element.type === Button && text(element).includes(label));
  const click = label => {
    const element = button(label);
    assert.ok(element, label);
    assert.equal(element.props.disabled, undefined, label);
    element.props.onClick();
  };
  return { render, button, click, cleanup, states };
}

const settle = () => new Promise(resolve => setImmediate(resolve));
const accepted = { task_id: taskId, task_status: "accepted", browser_session_id: null, outcome: null };
const observation = {
  observed_at: "2026-10-10T00:00:00Z",
  page: { title: "Synthetic BOSS page", url: "https://www.zhipin.com/", state: "ready", kind: "job_list", jobs: [{ job_id: "job-a", title: "Synthetic job", company: "Synthetic company" }], conversations: [], messages: [] },
};

test("historical resume cards restore without sending or claiming a current material version", async () => {
  const writes = [];
  const result = { ...observation, page: { ...observation.page, kind: "conversations", jobs: [],
    messages: [{ conversation_id: "thread-1", message_id: "123", sender: "candidate", content: "Synthetic.pdf", sent_at: null,
      resume_attachment: { filename: "Synthetic.pdf", sent_by_candidate: true, request_message_id: "122" } }] } };
  const fixture = taskCard(async (url, options = {}) => {
    if (options.method === "POST") writes.push(url);
    return Response.json(url.endsWith("/result") ? result : { ...accepted, task_status: "completed" });
  });
  await settle();
  assert.match(text(fixture.render()), /历史简历卡片.*我方消息.*Synthetic\.pdf/);
  assert.match(text(fixture.render()), /不能证明发送成功、待发送材料的版本或再次发送许可/);
  fixture.click("核对读取结果");
  await settle();
  assert.deepEqual(writes, []);
  fixture.cleanup();
});

test("selected conversation is persisted before execution and restored with message direction", async () => {
  let current = { ...accepted, task_status: "failed" };
  let detailed = false;
  const writes = [];
  const page = { ...observation.page, kind: "conversations", state: "unknown", jobs: [],
    conversations: [{ conversation_id: "thread-1", recruiter_name: "Synthetic HR", company: null, last_message: "Synthetic preview" }], messages: [] };
  const fixture = taskCard(async (url, options = {}) => {
    if (options.method === "POST") {
      writes.push({ url, options });
      if (url.endsWith("/run")) { current = { ...accepted, task_status: "completed" }; detailed = true; }
      else current = accepted;
      return Response.json(current);
    }
    return Response.json(url.endsWith("/result") ? { ...observation, page: { ...page,
      resume_control: detailed ? { conversation_id: "thread-1", state: "unavailable", attachment_reported: false, material_state: "absent" } : null,
      messages: detailed ? [{ message_id: "123", conversation_id: "thread-1", sender: "recruiter", content: "Synthetic detail", sent_at: null }] : [] } } : current);
  });
  await settle();
  fixture.button("读取会话详情").props.onClick();
  assert.match(text(fixture.render()), /标记已读/);
  fixture.click("允许并读取");
  await settle();
  assert.equal(JSON.parse(writes[0].options.body).conversation_id, "thread-1");
  assert.equal(writes.length, 2);
  assert.match(text(fixture.render()), /招聘方/);
  assert.match(text(fixture.render()), /Synthetic detail/);
  assert.match(text(fixture.render()), /简历入口： 页面当前不可用/);
  assert.match(text(fixture.render()), /不能据此自动发送/);
  fixture.click("核对读取结果");
  await settle();
  assert.equal(writes.length, 2);
  fixture.cleanup();
});

test("read card requires consent, runs the accepted task once and restores persisted results", async () => {
  let current = null;
  const writes = [];
  const fixture = taskCard(async (url, options = {}) => {
    if (options.method === "POST") {
      writes.push({ url, options });
      if (url.endsWith("/run")) {
        current = { ...accepted, task_status: "completed", outcome: "read_completed" };
        return Response.json(current);
      }
      current = accepted;
      return Response.json(current, { status: 201 });
    }
    return Response.json(url.endsWith("/result") ? (current?.task_status === "completed" ? observation : null) : current);
  });
  await settle();
  assert.equal(fixture.button("读取 BOSS 页面").props.disabled, false);
  fixture.button("读取 BOSS 页面").props.onClick();
  assert.equal(writes.length, 0);
  fixture.click("允许并读取");
  await settle();
  assert.equal(writes.length, 2);
  assert.deepEqual(JSON.parse(writes[0].options.body), { version: "v1", authorize_read: true });
  assert.ok(writes[0].options.headers["Idempotency-Key"]);
  assert.ok(writes[1].url.endsWith(`/${taskId}/run`));
  assert.match(text(fixture.render()), /读取完成/);
  assert.match(text(fixture.render()), /Synthetic job/);
  fixture.click("核对读取结果");
  await settle();
  assert.equal(writes.length, 2);
  fixture.cleanup();
});

test("lost run response is reconciled without replay and unknown task blocks another write", async () => {
  let current = null;
  let runs = 0;
  const fixture = taskCard(async (url, options = {}) => {
    if (options.method === "POST") {
      if (url.endsWith("/run")) {
        runs++;
        current = { ...accepted, task_status: "unknown", outcome: "read_unknown" };
        throw new TypeError("Lost response");
      }
      current = accepted;
    }
    return Response.json(url.endsWith("/result") ? observation : current);
  });
  await settle();
  fixture.button("读取 BOSS 页面").props.onClick();
  fixture.click("允许并读取");
  await settle();
  assert.match(text(fixture.render()), /结果待核对/);
  assert.match(text(fixture.render()), /本次任务尚未确认完成/);
  assert.equal(fixture.button("读取 BOSS 页面").props.disabled, true);
  fixture.click("核对读取结果");
  await settle();
  assert.equal(runs, 1);
  fixture.cleanup();
});

test("blocked viewer prevents accepting a new task and unmounted reads do not overwrite state", async () => {
  let resolve;
  const fixture = taskCard(() => new Promise(callback => { resolve = callback; }), true);
  const previous = [...fixture.states];
  assert.equal(fixture.button("读取 BOSS 页面").props.disabled, true);
  fixture.cleanup();
  resolve(Response.json(accepted));
  await settle();
  assert.deepEqual(fixture.states, previous);
});

test("persisted list previews do not claim a full message read or require login again", async () => {
  const partial = { ...observation, page: { ...observation.page, kind: "conversations", state: "unknown", jobs: [], conversations: [{ conversation_id: "synthetic-thread", recruiter_name: "Synthetic HR", company: null, last_message: "Synthetic preview" }], messages: [] } };
  const fixture = taskCard(async url => Response.json(url.endsWith("/result") ? partial : { ...accepted, task_status: "failed", outcome: "read_failed" }));
  await settle();
  assert.match(text(fixture.render()), /已读取会话列表摘要 · 消息详情待核验/);
  assert.match(text(fixture.render()), /Synthetic preview/);
  assert.match(text(fixture.render()), /未完成有效业务读取/);
  assert.doesNotMatch(text(fixture.render()), /读取完成|需要重新登录/);
  fixture.cleanup();
});

test("unknown read closes only after confirmed release and never reruns the attempt", async () => {
  let current = { ...accepted, task_status: "unknown", outcome: "read_unknown" };
  let confirmRelease = false;
  const writes = [];
  const fixture = taskCard(async (url, options = {}) => {
    if (options.method === "POST") {
      writes.push(url);
      assert.ok(url.endsWith("/reconcile"));
      if (!confirmRelease) return Response.json({}, { status: 409 });
      current = { ...current, task_status: "failed", outcome: "read_failed" };
    }
    return Response.json(url.endsWith("/result") ? null : current);
  });
  await settle();
  assert.equal(fixture.button("读取 BOSS 页面").props.disabled, true);
  fixture.button("核对释放并结束").props.onClick();
  await settle();
  assert.equal(fixture.button("读取 BOSS 页面").props.disabled, true);
  assert.match(text(fixture.render()), /浏览器释放尚未确认/);
  confirmRelease = true;
  fixture.button("核对释放并结束").props.onClick();
  await settle();
  assert.match(text(fixture.render()), /读取失败/);
  assert.equal(fixture.button("读取 BOSS 页面").props.disabled, false);
  assert.equal(writes.length, 2);
  fixture.cleanup();
});

test("read BFF validates both IDs and forwards only its fixed API path", async () => {
  const calls = [];
  const { readRequest } = loadSource("app/api/connections/boss/[connectionId]/read/_helpers.ts", {
    "@/app/api/projects/_helpers": {
      failure: (status, code) => Response.json({ code }, { status }),
      validProjectId: value => typeof value === "string" && /^[0-9a-f-]{36}$/i.test(value),
    },
    "../../_helpers": { forward: (...args) => { calls.push(args); return Response.json(null); } },
  });
  const request = new Request("https://careeract.example");
  for (const invalid of [{ connectionId: "../foreign", taskId }, { connectionId, taskId: "../foreign" }]) {
    assert.equal((await readRequest(request, { params: Promise.resolve(invalid) }, "POST", "run")).status, 422);
  }
  assert.equal(calls.length, 0);
  await readRequest(request, { params: Promise.resolve({ connectionId, taskId }) }, "POST", "run");
  assert.equal(calls[0][1], `/api/v1/connections/boss/${connectionId}/read/${taskId}/run`);
  assert.equal(calls[0][3], 120_000);
  await readRequest(request, { params: Promise.resolve({ connectionId, taskId }) }, "DELETE", "task");
  assert.equal(calls[1][3], 75_000);
});

test("stop uses a separate request during a running read and restores waiting release without rerun", async () => {
  let current = { ...accepted, task_status: "running", browser_session_id: "scene" };
  let released = false;
  const writes = [];
  const fixture = taskCard(async (url, options = {}) => {
    if (options.method === "DELETE") {
      writes.push({ url, options });
      assert.equal(options.body, "{}");
      assert.equal(options.headers["Content-Type"], "application/json");
      current = { ...current, task_status: released ? "cancelled" : "waiting", outcome: released ? "cancelled_after_stop" : "read_stop_requested" };
    } else {
      assert.ok(!options.method || options.method === "GET");
    }
    return Response.json(url.endsWith("/result") ? null : current);
  });
  await settle();
  fixture.button("停止读取").props.onClick();
  await settle();
  assert.match(text(fixture.render()), /等待浏览器释放核验/);
  assert.equal(fixture.button("读取 BOSS 页面").props.disabled, true);
  released = true;
  fixture.button("核对停止并释放").props.onClick();
  await settle();
  assert.match(text(fixture.render()), /已取消/);
  assert.equal(fixture.button("读取 BOSS 页面").props.disabled, false);
  assert.equal(writes.length, 2);
  fixture.cleanup();
});
