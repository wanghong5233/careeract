import assert from "node:assert/strict";
import test from "node:test";
import { loadSource } from "./load-source.mjs";

const { selectConversationRange, deleteConversationSelection } = loadSource("lib/conversation-selection.ts");

test("range selection uses visible order, supports reverse and additive ranges, and ignores missing anchors", () => {
  const order = ["pinned", "project", "recent", "archive"];
  assert.deepEqual(selectConversationRange(order, [], "project", "archive", true, false), ["project", "recent", "archive"]);
  assert.deepEqual(selectConversationRange(order, [], "archive", "project", true, false), ["project", "recent", "archive"]);
  assert.deepEqual(selectConversationRange(order, ["pinned"], "recent", "archive", true, true), ["pinned", "recent", "archive"]);
  assert.deepEqual(selectConversationRange(order, ["gone", "recent"], "gone", "archive", true, false), ["recent", "archive"]);
  assert.deepEqual(selectConversationRange(order, ["recent"], null, "recent", false, true), []);
});

test("batch deletion stops at an uncertain item, retains remaining versions, and never retries automatically", async () => {
  const items = [{ id: "one", version: "v1" }, { id: "two", version: "v2" }, { id: "three", version: "v3" }];
  const calls = [];
  const failure = new Error("unknown result");
  const result = await deleteConversationSelection(items, async (id, version) => {
    calls.push([id, version]);
    if (id === "two") throw failure;
  });
  assert.deepEqual(calls, [["one", "v1"], ["two", "v2"]]);
  assert.equal(result.deleted, 1);
  assert.equal(result.error, failure);
  assert.deepEqual(result.remaining, items.slice(1));
  assert.equal(items.length, 3);
  const completed = await deleteConversationSelection(items, async () => {});
  assert.equal(completed.deleted, 3);
  assert.deepEqual(completed.remaining, []);
});
