import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { loadSource } from "./load-source.mjs";

const runtime = loadSource("lib/agent-runtime.ts");
const presentation = loadSource("lib/conversation-presentation.ts", { "@/lib/agent-runtime": runtime });
const syntheticMessage = (id, role, runId, status, content = "合成内容") => ({ id, role, run_id: runId, run_status: status, content, created_at: 1 });

test("unanswered status stays next to its own turn, before the next user message", () => {
  const messages = [syntheticMessage("first", "user", "cancelled", "CANCELLED"), syntheticMessage("second", "user", "completed", "COMPLETED"), syntheticMessage("reply", "assistant", "completed", "COMPLETED")];
  const converted = presentation.historyThreadMessages(messages, [{ run_id: "cancelled", status: "CANCELLED" }, { run_id: "completed", status: "COMPLETED" }]);
  assert.deepEqual(converted.map(message => message.id), ["first", "run-status:cancelled", "second", "reply"]);
  assert.deepEqual(converted[1].status, { type: "incomplete", reason: "cancelled" });
  assert.equal(converted[1].metadata.custom.noSavedReply, true);
  assert.equal(converted[3].metadata.custom.noSavedReply, undefined);
});

test("saved partial replies retain their state without duplicate status messages", () => {
  for (const status of ["CANCELLED", "ERROR", "UNKNOWN", "PAUSED", "RUNNING", "PENDING"]) {
    const messages = [syntheticMessage("user", "user", "run", status), syntheticMessage("reply", "assistant", "run", status)];
    const converted = presentation.historyThreadMessages(messages, [{ run_id: "run", status }]);
    assert.equal(converted.length, 2);
    assert.equal(converted[1].status.type, "incomplete");
    assert.equal(converted[1].metadata.custom.runStatus, status);
  }
});

test("missing or truncated user messages do not hide an unanswered failed run", () => {
  assert.equal(presentation.historyThreadMessages([], [{ run_id: "failed", status: "ERROR" }])[0].status.reason, "error");
  assert.deepEqual(presentation.historyThreadMessages([], undefined), []);
  assert.deepEqual(presentation.historyThreadMessages([], [{ run_id: "completed", status: "COMPLETED" }]), []);
});

const styles = { default: new Proxy({}, { get: (_, name) => String(name) }) };
const utils = { cn: (...values) => values.filter(Boolean).join(" ") };
const tooltip = { TooltipIconButton: props => React.createElement("button", { type: "button", className: props.className, "aria-label": props["aria-label"] }, props.children) };
const markdown = loadSource("components/markdown-text.tsx", {
  "@assistant-ui/react-markdown/styles/dot.css": {},
  "@/components/tooltip-icon-button": tooltip,
  "@/hooks/use-copy-to-clipboard": { useCopyToClipboard: () => ({ isCopied: false, copyToClipboard() {} }) },
  "@/lib/utils": utils,
});
const components = loadSource("components/conversation-messages.tsx", {
  "@/components/markdown-text": markdown, "@/components/tooltip-icon-button": tooltip,
  "@/lib/utils": utils, "./agent-space.module.css": styles,
});
const history = loadSource("components/conversation-history.tsx", {
  "@/components/conversation-messages": components, "@/lib/conversation-presentation": presentation,
});

test("real assistant-ui history renders Markdown and puts cancelled status before the next turn", () => {
  const messages = [
    syntheticMessage("user1", "user", "cancelled", "CANCELLED", "合成用户一"),
    syntheticMessage("reply1", "assistant", "cancelled", "CANCELLED", "## 合成标题\n\n- English 中文\n\n> 合成引用\n\n```python\nprint('synthetic')\n```\n\n| 列一 | 列二 |\n| --- | --- |\n| A | B |"),
    syntheticMessage("user2", "user", "complete", "COMPLETED", "合成用户二"),
  ];
  const html = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages }));
  for (const tag of ["h2", "ul", "blockquote", "pre", "table"]) assert.match(html, new RegExp(`<${tag}[ >]`));
  assert.ok(html.indexOf("已取消") < html.indexOf("合成用户二"));
  assert.equal((html.match(/已取消/g) ?? []).length, 1);
  assert.match(html, /class="userMessage"/);
  assert.match(html, /data-prompt-id="user1"/);
  assert.match(html, /aria-label="复制消息"/);
  assert.match(html, /aria-label="对话轮次导航"/);
  assert.match(html, /跳到第 2 条消息/);
  assert.match(html, /返回最新消息/);
});

test("failed, cancelled and unknown history have distinct, truthful presentation", () => {
  for (const [status, label, isError] of [["ERROR", "运行失败", true], ["CANCELLED", "已取消", false], ["UNKNOWN", "运行状态未确认", false], ["PAUSED", "等待继续", false]]) {
    const html = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [syntheticMessage("user", "user", "run", status)], runs: [{ run_id: "run", status }] }));
    assert.match(html, new RegExp(label));
    assert.match(html, /本次运行没有已保存的回复/);
    assert.equal(html.includes("messageStatusError"), isError);
    assert.doesNotMatch(html, /已完成/);
  }
});

test("completed replies have no incomplete status footer", () => {
  const html = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [syntheticMessage("reply", "assistant", "run", "COMPLETED")] }));
  assert.doesNotMatch(html, /请核对已显示内容|运行失败|已取消|运行状态未确认/);
});

test("live and saved replies use identical Markdown and message presentation", () => {
  const messages = [syntheticMessage("reply", "assistant", "run", "COMPLETED", "## 中文 English\n\n- 合成内容")];
  const saved = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages }));
  const live = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [], liveMessages: presentation.historyThreadMessages(messages) }));
  assert.equal(live, saved);
});

test("live display distinguishes waiting, streaming and incomplete output without inventing completion", () => {
  const waiting = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [], liveMessages: [{ id: "user", role: "user", content: "合成请求" }], isRunning: true }));
  assert.match(waiting, /正在等待回复/);
  const streaming = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [], liveMessages: [{ id: "reply", role: "assistant", content: "合成部分回复", status: { type: "running" } }], isRunning: true }));
  assert.match(streaming, /正在生成/);
  assert.doesNotMatch(streaming, /已取消|运行失败|运行状态未确认/);
  const interrupted = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [], liveMessages: [{ id: "reply", role: "assistant", content: "合成部分回复", status: { type: "incomplete", reason: "other" } }] }));
  assert.match(interrupted, /运行状态未确认/);
  assert.doesNotMatch(interrupted, /正在生成|已完成/);
});
