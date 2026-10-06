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
  "@/components/ui/collapsible": loadSource("components/ui/collapsible.tsx"),
  "@/components/message-actions": { useMessageActions: () => React.useContext(messageActions) },
  "@/components/ui/button": { Button: props => React.createElement("button", { type: props.type, disabled: props.disabled, onClick: props.onClick }, props.children) },
  "@/components/markdown-text": markdown, "@/components/tooltip-icon-button": tooltip,
  "@/lib/utils": utils, "./agent-space.module.css": styles,
  "@/lib/run-presentation": loadSource("lib/run-presentation.ts"),
});

const messageActions = React.createContext({});

test("duration uses saved framework metrics and never invents missing or invalid timing", () => {
  const format = loadSource("lib/run-presentation.ts").formatRunDuration;
  assert.equal(format(65.9), "1分5秒");
  assert.equal(format(0), "0秒");
  for (const value of [undefined, null, -1, NaN, Infinity, "10"]) assert.equal(format(value), null);
  const message = { ...syntheticMessage("reply", "assistant", "run", "CANCELLED"), run_duration_seconds: 8.4 };
  const html = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [message] }));
  assert.match(html, /用时 8秒/);
  assert.match(html, /已取消/);
  assert.doesNotMatch(html, /已完成|本页计时/);
});

test("tool-separated replies display saved run duration once", () => {
  const messages = ["before-tool", "after-tool"].map(id => ({ ...syntheticMessage(id, "assistant", "same-run", "COMPLETED"), run_duration_seconds: 9 }));
  const converted = presentation.historyThreadMessages(messages);
  assert.equal(converted[0].metadata.custom.runDurationSeconds, 9);
  assert.equal(converted[1].metadata.custom.runDurationSeconds, undefined);
});
const history = loadSource("components/conversation-history.tsx", {
  "@/components/message-actions": { MessageActionsContext: messageActions },
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

test("answer toolbar keeps copying and timestamps separate from completed-only branch and feedback actions", () => {
  const messages = [syntheticMessage("input", "user", "run", "COMPLETED"), syntheticMessage("reply", "assistant", "run", "COMPLETED")];
  const html = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages, onQuote() {}, onBranch() {}, onAddToConversation() {} }));
  assert.equal((html.match(/class="assistantActions"/g) ?? []).length, 1);
  assert.match(html, /分支到新聊天/);
  assert.match(html, /aria-label="复制回答"/);
  assert.match(html, /<time[^>]*dateTime="1970-01-01T00:00:01.000Z"/);
  assert.doesNotMatch(html, /回答有帮助|回答需要改进/);
  assert.doesNotMatch(html, /在侧聊中打开|在侧聊中追问/);
  assert.equal((html.match(/data-aui-quote-selectable="true"/g) ?? []).length, 1);
  const readonly = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages }));
  assert.doesNotMatch(readonly, /data-aui-quote-selectable="true"/);
  assert.match(readonly, /aria-label="复制回答"/);
  assert.doesNotMatch(readonly, /分支到新聊天/);
  const withFeedback = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages, onFeedback() {} }));
  assert.match(withFeedback, /aria-label="回答有帮助"/);
  assert.match(withFeedback, /aria-label="回答需要改进"/);
  for (const status of ["RUNNING", "CANCELLED", "ERROR", "UNKNOWN"]) {
    const incomplete = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [syntheticMessage("reply", "assistant", "run", status)], onBranch() {}, onFeedback() {} }));
    assert.doesNotMatch(incomplete, /分支到新聊天|回答有帮助|回答需要改进/);
    assert.match(incomplete, /aria-label="复制回答"/);
  }
});

test("message time uses real saved or supplied live timestamps and never fills missing dates with now", () => {
  const format = loadSource("lib/run-presentation.ts").formatMessageTimestamp;
  const timestamp = Date.parse("2026-10-04T09:32:00Z");
  assert.deepEqual(format(timestamp, "Asia/Shanghai"), {
    dateTime: "2026-10-04T09:32:00.000Z", label: "星期日 17:32", title: "2026年10月4日星期日 17:32",
  });
  for (const value of [undefined, null, 0, -1, NaN, Infinity, "10", 1e20]) assert.equal(format(value), null);
  const saved = { ...syntheticMessage("reply", "assistant", "run", "COMPLETED"), created_at: timestamp / 1000 };
  const html = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [saved] }));
  assert.match(html, /dateTime="2026-10-04T09:32:00.000Z"/);
  const missing = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [{ ...saved, created_at: 0 }] }));
  assert.doesNotMatch(missing, /<time /);
  const live = [{ id: "live", role: "assistant", content: "合成回答", createdAt: new Date(timestamp) }];
  assert.equal(presentation.groupLiveAssistantMessages(live)[0].metadata.custom.messageCreatedAt, timestamp);
  assert.equal(presentation.groupLiveAssistantMessages([{ ...live[0], createdAt: undefined }])[0].metadata.custom.messageCreatedAt, undefined);
});

test("live and saved replies use identical Markdown and message presentation", () => {
  const messages = [syntheticMessage("reply", "assistant", "run", "COMPLETED", "## 中文 English\n\n- 合成内容")];
  const saved = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages }));
  const live = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [], liveMessages: presentation.historyThreadMessages(messages) }));
  assert.equal(live, saved);
});

test("inline editing replaces only the selected prompt and preserves the source reply", () => {
  const messages = [syntheticMessage("older", "user", "first", "COMPLETED", "旧输入"), syntheticMessage("input", "user", "run", "COMPLETED", "原输入"), syntheticMessage("reply", "assistant", "run", "COMPLETED", "原回答保留")];
  const editing = { id: "input", text: "修改后的多行\n**原文**", busy: false, error: "合成分支失败", onChange() {}, onCancel() {}, onSubmit() {} };
  const html = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages, onEdit() {}, editing }));
  assert.equal((html.match(/<textarea/g) ?? []).length, 1);
  assert.match(html, /修改后的多行\n\*\*原文\*\*/);
  assert.match(html, /原回答保留/);
  assert.match(html, /旧输入/);
  assert.match(html, /发送到独立分支，原对话及后续历史保留/);
  assert.match(html, /role="alert"[^>]*>合成分支失败/);
  assert.doesNotMatch(html, /role="dialog"|编辑并另建分支/);
  const closed = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages, onEdit() {} }));
  assert.match(closed, /原输入/);
  assert.equal((closed.match(/aria-label="编辑消息"/g) ?? []).length, 1);
  assert.doesNotMatch(closed, /textarea/);
});

test("inline editor guards blank/busy sends, keeps IME input and supports cancel/shortcut", () => {
  let submitted = 0;
  let cancelled = 0;
  let requested = 0;
  let changed;
  const editing = { id: "input", text: "合成修改", busy: false, onChange(text) { changed = text; }, onCancel() { cancelled++; }, onSubmit() { submitted++; } };
  const form = components.MessageEditForm({ editing });
  const textarea = form.props.children[0];
  const event = { preventDefault() {}, nativeEvent: { isComposing: false }, currentTarget: { form: { requestSubmit() { requested++; } } } };
  textarea.props.onChange({ target: { value: "多行\nMarkdown" } });
  assert.equal(changed, "多行\nMarkdown");
  form.props.onSubmit(event);
  assert.equal(submitted, 1);
  textarea.props.onKeyDown({ ...event, key: "Enter", ctrlKey: true });
  textarea.props.onKeyDown({ ...event, key: "Enter", metaKey: true });
  textarea.props.onKeyDown({ ...event, key: "Enter", ctrlKey: true, nativeEvent: { isComposing: true } });
  assert.equal(requested, 2);
  textarea.props.onKeyDown({ ...event, key: "Escape" });
  assert.equal(cancelled, 1);
  editing.busy = true;
  form.props.onSubmit(event);
  textarea.props.onKeyDown({ ...event, key: "Escape" });
  assert.equal(submitted, 1);
  assert.equal(cancelled, 1);
  const busyHtml = renderToStaticMarkup(React.createElement(components.MessageEditForm, { editing }));
  assert.match(busyHtml, /textarea[^>]*disabled/);
  assert.match(busyHtml, /正在创建/);
  editing.busy = false;
  editing.text = " \n ";
  form.props.onSubmit(event);
  assert.equal(submitted, 1);
});

test("navigation jumps immediately during a run so streaming follow does not interrupt a smooth jump", () => {
  for (const running of [true, false]) {
    const jumps = [];
    const target = { dataset: { promptId: "first" }, scrollIntoView: options => jumps.push(options) };
    const view = loadSource("components/conversation-messages.tsx", {
      "@/components/ui/collapsible": {},
      react: { useRef: () => ({ current: { querySelectorAll: () => [target] } }), useState: () => [null, () => {}], useEffect() {} },
      "@assistant-ui/react": { ThreadPrimitive: { Root: "root", Viewport: "viewport", Messages: "messages", ViewportFooter: "footer", ScrollToBottom: "bottom" }, useAuiState: selector => selector({ thread: { isRunning: running, messages: ["first", "second"].map(id => ({ id, role: "user", content: [{ type: "text", text: id }] })) } }) },
      "@/components/message-actions": { useMessageActions: () => ({}) },
      "@/components/ui/button": {}, "@/components/markdown-text": {}, "@/components/tooltip-icon-button": tooltip,
      "@/lib/utils": utils, "./agent-space.module.css": styles, "@/lib/run-presentation": {},
    }, { window: { matchMedia: () => ({ matches: false }) } });
    const navigationElement = view.ConversationMessages({}).props.children[0];
    const navigation = navigationElement.type(navigationElement.props);
    navigation.props.children[0].props.onClick();
    assert.deepEqual(jumps, [{ block: "start", behavior: running ? "instant" : "smooth" }]);
  }
});

test("saved timing stays visible while a subsequent reply streams", () => {
  const message = { ...syntheticMessage("reply", "assistant", "run", "COMPLETED"), run_duration_seconds: 5 };
  const live = [...presentation.historyThreadMessages([message]).map(item => ({ ...item, metadata: undefined })), { id: "new", role: "assistant", content: "合成流", status: { type: "running" } }];
  const html = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [message], liveMessages: live, isRunning: true }));
  assert.match(html, /用时 5秒/);
  assert.match(html, /正在生成/);
});

test("live tool process separates commentary and final answer without exposing tool payloads", () => {
  const input = { id: "input", role: "user", content: "合成问题" };
  const tool = { type: "tool-call", toolCallId: "tool", toolName: "检索公开网页", args: { private: "hidden" }, argsText: "hidden", result: { status: "COMPLETED", duration_seconds: 2.4 } };
  const grouped = presentation.groupLiveAssistantMessages([input, { id: "progress", role: "assistant", content: [{ type: "text", text: "正在检索" }, tool] }, { id: "final", role: "assistant", content: "合成回答", status: { type: "complete", reason: "stop" } }]);
  assert.equal(grouped.length, 2);
  assert.equal(grouped[1].id, "final");
  assert.equal(grouped[1].content, "合成回答");
  assert.deepEqual(grouped[1].metadata.custom.runProcess, [{ id: "progress", kind: "message", content: "正在检索" }, { id: "tool", kind: "tool", label: "检索公开网页", status: "COMPLETED", duration_seconds: 2.4 }]);
  assert.doesNotMatch(JSON.stringify(grouped), /hidden|private/);
  const cancelled = presentation.groupLiveAssistantMessages([input, { id: "pending", role: "assistant", content: [{ ...tool, result: undefined }], status: { type: "incomplete", reason: "cancelled" } }]);
  assert.equal(cancelled[1].metadata.custom.runProcess[0].status, "CANCELLED");
});

test("saved process has a real accessible disclosure and cancelled process stays cancelled", () => {
  const message = { ...syntheticMessage("reply", "assistant", "run", "CANCELLED"), run_duration_seconds: 3, process: [{ id: "tool", kind: "tool", label: "检索公开网页", status: "CANCELLED" }] };
  const html = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [message] }));
  assert.match(html, /aria-label="运行过程"/);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /用时 3秒/);
  assert.match(html, /已取消/);
  assert.doesNotMatch(html, /已完成/);
  const empty = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [syntheticMessage("reply", "assistant", "run", "COMPLETED")] }));
  assert.doesNotMatch(empty, /aria-label="运行过程"/);
});

test("reconciled terminal history cannot revert to cached active state when the next reply streams", () => {
  for (const [status, label] of [["INTERRUPTED", "运行中断 · 结果未知"], ["CANCELLED", "已取消"], ["ERROR", "运行失败"]]) {
    const saved = syntheticMessage("prior", "assistant", "prior-run", status);
    const stale = presentation.historyThreadMessages([{ ...saved, run_status: "RUNNING" }]);
    const live = [...stale, { id: "new", role: "assistant", content: "合成流", status: { type: "running" } }];
    const html = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [saved], liveMessages: live, isRunning: true }));
    assert.match(html, new RegExp(label));
    assert.match(html, /正在生成/);
    assert.doesNotMatch(html, /运行尚未结束/);
  }
});

test("saved pending history cannot replace a genuinely streaming reply", () => {
  const saved = syntheticMessage("reply", "assistant", "run", "PENDING");
  const live = [{ id: "reply", role: "assistant", content: "合成流", status: { type: "running" } }];
  const html = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [saved], liveMessages: live, isRunning: true }));
  assert.match(html, /正在生成/);
  assert.doesNotMatch(html, /运行尚未结束/);
});

test("a runtime without hydrated old messages keeps saved history while the next turn streams", () => {
  const saved = [syntheticMessage("old-user", "user", "old", "INTERRUPTED", "合成旧输入"), syntheticMessage("old-reply", "assistant", "old", "INTERRUPTED", "合成旧片段")];
  const live = [{ id: "new-user", role: "user", content: "合成新输入" }, { id: "new-reply", role: "assistant", content: "合成新片段", status: { type: "running" } }];
  const html = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: saved, liveMessages: live, isRunning: true }));
  assert.ok(html.indexOf("合成旧输入") < html.indexOf("合成新输入"));
  assert.match(html, /合成旧片段/);
  assert.match(html, /运行中断 · 结果未知/);
  assert.match(html, /正在生成/);
});

test("framework-restored IDs do not duplicate a saved prefix and identical new prompts remain", () => {
  const saved = [syntheticMessage("saved-user", "user", "old", "COMPLETED", "合成重复输入"), syntheticMessage("saved-reply", "assistant", "old", "COMPLETED", "合成旧答复")];
  const restored = presentation.historyThreadMessages(saved).map((message, index) => ({ ...message, id: `framework-${index}` }));
  const live = [...restored, { id: "new-user", role: "user", content: "合成重复输入" }, { id: "new-reply", role: "assistant", content: "合成新回复", status: { type: "running" } }];
  const html = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: saved, liveMessages: live, isRunning: true }));
  assert.equal((html.match(/合成旧答复/g) ?? []).length, 1);
  assert.equal((html.match(/data-prompt-id=/g) ?? []).length, 2);
  const unhydrated = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: saved, liveMessages: live.slice(2), isRunning: true }));
  assert.equal((unhydrated.match(/data-prompt-id=/g) ?? []).length, 2);
});

test("live display distinguishes waiting, streaming and incomplete output without inventing completion", () => {
  const waiting = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [], liveMessages: [{ id: "user", role: "user", content: "合成请求" }], isRunning: true }));
  assert.match(waiting, /正在等待回复/);
  const streaming = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [], liveMessages: [{ id: "reply", role: "assistant", content: "合成部分回复", status: { type: "running" } }], isRunning: true }));
  assert.match(streaming, /正在生成/);
  assert.doesNotMatch(streaming, /已取消|运行失败|运行状态未确认/);
  assert.doesNotMatch(streaming, /aria-label="复制回答"|分支到新聊天|回答有帮助|回答需要改进/);
  const interrupted = renderToStaticMarkup(React.createElement(history.ConversationHistory, { messages: [], liveMessages: [{ id: "reply", role: "assistant", content: "合成部分回复", status: { type: "incomplete", reason: "other" } }] }));
  assert.match(interrupted, /运行状态未确认/);
  assert.doesNotMatch(interrupted, /正在生成|已完成/);
});
