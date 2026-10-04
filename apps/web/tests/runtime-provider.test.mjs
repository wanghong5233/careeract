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
