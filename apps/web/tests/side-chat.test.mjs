import assert from "node:assert/strict";
import test from "node:test";
import { loadSource } from "./load-source.mjs";

const source = loadSource("lib/side-chat-state.ts");

test("side chat view preserves hidden history and original multiline quote across refresh", () => {
  const state = { chat: { session_id: "side:synthetic", temporary_until: "2026-10-06T00:00:00Z", side_context: { source_id: "conversation:main", quote: "合成\n原文" } }, tabId: "synthetic-tab", draft: "合成草稿", hidden: true, suppressCloseWarning: true };
  assert.deepEqual(source.readSideChatView(JSON.stringify(state)), state);
  assert.equal(source.appendSideQuote("已有草稿", "中文\n**English**"), "已有草稿\n\n> 中文\n> **English**\n\n");
  for (const value of [null, "broken", "{}", '{"chat":{}}']) assert.equal(source.readSideChatView(value).chat, null);
});

test("temporary side history and draft stay separate from regular directory and owner", () => {
  const storage = new Map();
  const state = loadSource("lib/side-chat-state.ts", {}, { window: {}, sessionStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) }, crypto: { randomUUID: () => "synthetic-tab" } });
  const first = state.getSideChatStore("synthetic-owner");
  first.update(previous => ({ ...previous, draft: "侧聊草稿", hidden: false }));
  assert.equal(state.getSideChatStore("synthetic-other").snapshot().draft, "");
  assert.equal(state.readSideChatView(storage.get("careeract-side:synthetic-owner")).draft, "侧聊草稿");
  assert.equal(first.snapshot().tabId, "synthetic-tab");
});
