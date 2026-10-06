import assert from "node:assert/strict";
import test from "node:test";
import { loadSource } from "./load-source.mjs";

test("saved message view exposes only the latest input for editing and retains cancelled status", () => {
  let displayed;
  const actions = { Provider: "message-actions" };
  const presentation = loadSource("lib/conversation-presentation.ts", { "@/lib/agent-runtime": loadSource("lib/agent-runtime.ts") });
  const view = loadSource("components/conversation-history.tsx", {
    react: { useMemo: callback => callback() },
    "@assistant-ui/react": { AssistantRuntimeProvider: "runtime", useExternalStoreRuntime: options => { displayed = options.messages; return options; } },
    "@/components/conversation-messages": { ConversationMessages: "messages" },
    "@/components/message-actions": { MessageActionsContext: actions },
    "@/lib/conversation-presentation": presentation,
  });
  const messages = [
    { id: "first", role: "user", content: "原始问题\n第二行", run_id: "one", run_status: "COMPLETED", created_at: 1 },
    { id: "answer", role: "assistant", content: "原始回答", run_id: "one", run_status: "COMPLETED", created_at: 2 },
    { id: "latest", role: "user", content: "取消的问题", run_id: "two", run_status: "CANCELLED", created_at: 3 },
  ];
  const edit = () => {};
  const branch = () => {};
  const feedback = () => {};
  const result = view.ConversationHistory({ messages, runs: [{ run_id: "two", status: "CANCELLED" }], onEdit: edit, onBranch: branch, onFeedback: feedback });
  assert.equal(result.props.value.editId, "latest");
  assert.equal(result.props.value.edit, edit);
  assert.equal(result.props.value.branch, branch);
  assert.equal(result.props.value.feedback, feedback);
  assert.equal(displayed.at(-1).status.reason, "cancelled");
  assert.equal(displayed[0].content, "原始问题\n第二行");
  assert.equal(messages.length, 3);
  assert.equal(view.ConversationHistory({ messages }).props.value.edit, undefined);
});

test("branch creation forwards the exact boundary and version and reports conflicts", async () => {
  const calls = [];
  const client = loadSource("lib/agent-conversations.ts", { "@/lib/privacy": {} }, {
    fetch: async (url, init) => { calls.push({ url, body: JSON.parse(init.body) }); return new Response("{}", { status: 409 }); },
  });
  const body = { id: "stable", version: "v1", message_id: "saved-input", mode: "before", title: "编辑分支" };
  await assert.rejects(client.createConversationBranch("conversation:source", body), /输入已保留/);
  assert.equal(calls[0].url, "/api/agent/conversations/conversation%3Asource/branch");
  assert.deepEqual(calls[0].body, body);
});
