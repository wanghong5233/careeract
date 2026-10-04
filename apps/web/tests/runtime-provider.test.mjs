import assert from "node:assert/strict";
import test from "node:test";
import { loadSource } from "./load-source.mjs";

const runtimeProvider = loadSource("lib/agent-runtime.ts");

test("runtime history is addressed by the selected conversation", () => {
  assert.equal(runtimeProvider.conversationHistoryUrl("conversation:synthetic"), "/api/agent/history?session_id=conversation%3Asynthetic&limit=100");
});

test("runtime key changes for every selected conversation", () => {
  assert.equal(runtimeProvider.conversationRuntimeKey("conversation:first", "draft:first"), "conversation:first");
  assert.equal(runtimeProvider.conversationRuntimeKey(undefined, "draft:first"), "draft:draft:first");
  assert.notEqual(runtimeProvider.conversationRuntimeKey(undefined, "draft:first"), runtimeProvider.conversationRuntimeKey(undefined, "draft:second"));
});

test("runtime history keeps non-completed run states incomplete", () => {
  assert.deepEqual(runtimeProvider.historyMessageStatus("COMPLETED"), { type: "complete", reason: "stop" });
  assert.deepEqual(runtimeProvider.historyMessageStatus("CANCELLED"), { type: "incomplete", reason: "cancelled" });
  assert.deepEqual(runtimeProvider.historyMessageStatus("ERROR"), { type: "incomplete", reason: "error" });
  assert.deepEqual(runtimeProvider.historyMessageStatus("RUNNING"), { type: "incomplete", reason: "other" });
  assert.deepEqual(runtimeProvider.historyMessageStatus("UNKNOWN"), { type: "incomplete", reason: "other" });
});

test("runtime send queue is isolated by owner and selected conversation", () => {
  runtimeProvider.queueConversationSend("owner-one", "conversation:first", "合成消息");
  assert.equal(runtimeProvider.takeConversationSend("owner-two", "conversation:first"), undefined);
  assert.equal(runtimeProvider.takeConversationSend("owner-one", "conversation:second"), undefined);
  assert.equal(runtimeProvider.takeConversationSend("owner-one", "conversation:first"), "合成消息");
  assert.equal(runtimeProvider.takeConversationSend("owner-one", "conversation:first"), undefined);
});

test("runtime stream rejects a disconnect without a terminal event", async () => {
  const response = new Response("data: {\"type\":\"RUN_STARTED\"}\n\n");
  const guarded = runtimeProvider.requireFinishedStream(response);
  await assert.rejects(guarded.text(), /连接已中断/);
});

test("runtime stream accepts a terminal event split across chunks", async () => {
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode("data: {\"type\":\"RUN_STAR"));
      controller.enqueue(new TextEncoder().encode("TED\"}\n\ndata: {\"type\":\"RUN_FINISHED\"}\n\n"));
      controller.close();
    },
  });
  const guarded = runtimeProvider.requireFinishedStream(new Response(stream));
  assert.match(await guarded.text(), /RUN_FINISHED/);
});
