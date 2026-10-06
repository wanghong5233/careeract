import assert from "node:assert/strict";
import test from "node:test";
import { loadSource } from "./load-source.mjs";

function stateFixture(stored = new Map(), blocked = false) {
  const sessionStorage = {
    getItem: key => { if (blocked) throw new Error("storage denied"); return stored.get(key) ?? null; },
    setItem: (key, value) => { if (blocked) throw new Error("storage denied"); stored.set(key, value); },
    get length() { return stored.size; },
    key: index => [...stored.keys()][index],
    removeItem: key => stored.delete(key),
  };
  return loadSource("lib/agent-space-state.ts", {}, { window: {}, sessionStorage });
}

test("new conversation leaves the current content and preserves previous drafts", () => {
  const { beginSpaceConversation, newSpaceConversation } = stateFixture();
  const previous = { ...newSpaceConversation("old", "project"), draft: "kept", tabs: [{ href: "/workspace/background", label: "背景" }], activeHref: "/workspace/background" };
  const result = beginSpaceConversation({ conversations: [previous], selectedId: "old", navigation: true, panelWidth: 50 }, "next");
  assert.equal(result.selectedId, "next");
  assert.equal(result.conversations[0].activeHref, "/workspace");
  assert.equal(result.conversations[0].panelHidden, true);
  assert.equal(result.conversations[0].projectId, null);
  assert.deepEqual(result.conversations[1], previous);
});

test("blank conversation reuse is scoped to the project and resets the old route", () => {
  const { beginSpaceConversation, newSpaceConversation } = stateFixture();
  const state = { conversations: [{ ...newSpaceConversation("blank", "one"), activeHref: "/workspace/background" }], selectedId: "blank", navigation: true, panelWidth: 50 };
  assert.equal(beginSpaceConversation(state, "other", "one").selectedId, "blank");
  assert.equal(beginSpaceConversation(state, "other", "one").conversations[0].activeHref, "/workspace");
  assert.equal(beginSpaceConversation(state, "other", "two").conversations.length, 2);
});

test("project deletion detaches conversations and keeps draft, archive state and unrelated material tabs", () => {
  const { removeSpaceProject, newSpaceConversation } = stateFixture();
  const material = { href: "/workspace/library?material=kept", label: "材料" };
  const state = { conversations: [{ ...newSpaceConversation("one", "project"), draft: "kept", archived: true, activeHref: "/workspace/projects/project?view=all", tabs: [{ href: "/workspace/projects/project", label: "项目" }, material] }], selectedId: "one", navigation: true, panelWidth: 50 };
  const result = removeSpaceProject(state, "project");
  assert.equal(result.conversations[0].projectId, null);
  assert.equal(result.conversations[0].draft, "kept");
  assert.equal(result.conversations[0].archived, true);
  assert.equal(result.conversations[0].activeHref, "/workspace");
  assert.deepEqual(result.conversations[0].tabs, [material]);
  assert.equal(state.conversations[0].projectId, "project");
});

test("conversation removal clears only the selected chat and opens a blank without losing other drafts", () => {
  const { removeSpaceConversation, newSpaceConversation } = stateFixture();
  const kept = { ...newSpaceConversation("kept"), draft: "保留草稿", archived: true };
  const state = { conversations: [newSpaceConversation("deleted"), kept], selectedId: "deleted", navigation: true, panelWidth: 50 };
  const result = removeSpaceConversation(state, "deleted");
  assert.equal(result.conversations.length, 2);
  assert.equal(result.conversations[0].draft, "");
  assert.equal(result.conversations[0].id, result.selectedId);
  assert.deepEqual(result.conversations[1], kept);
  assert.equal(removeSpaceConversation({ ...state, selectedId: "kept" }, "deleted").selectedId, "kept");
  assert.equal(state.conversations.length, 2);
});

test("draft storage restores across module reload and isolates owners and tabs", () => {
  const stored = new Map();
  const first = stateFixture(stored);
  const store = first.getSpaceStore("owner-one");
  store.snapshot();
  store.update(state => ({ ...state, conversations: [{ ...state.conversations[0], draft: "private draft" }] }));
  assert.equal(stateFixture(stored).getSpaceStore("owner-one").snapshot().conversations[0].draft, "private draft");
  assert.equal(first.getSpaceStore("owner-two").snapshot().conversations[0].draft, "");
  assert.equal(stateFixture().getSpaceStore("owner-one").snapshot().conversations[0].draft, "");
  stored.set("unrelated", "keep");
  first.clearSpaceDrafts();
  assert.deepEqual([...stored], [["unrelated", "keep"]]);
  assert.equal(first.getSpaceStore("owner-one").snapshot().conversations[0].draft, "");
});

test("invalid stored routes are rejected and denied storage remains usable in memory", () => {
  const { getSpaceStore } = stateFixture(new Map([["careeract-space:owner", JSON.stringify({ conversations: [{ id: "x", projectId: null, title: "x", draft: "", archived: false, tabs: [{ href: "https://evil.example", label: "x" }] }], selectedId: "x", navigation: true, panelWidth: 50 })]]));
  assert.equal(getSpaceStore("owner").snapshot().selectedId, "new");
  const denied = stateFixture(new Map(), true).getSpaceStore("owner");
  denied.snapshot();
  assert.equal(denied.storageAvailable(), false);
  denied.update(state => ({ ...state, panelWidth: 40 }));
  assert.equal(denied.snapshot().panelWidth, 40);
  assert.equal(denied.storageAvailable(), false);
});

test("latest request cancels its predecessor and rejects late responses after changes or unmount", () => {
  const { createLatestRequest } = loadSource("lib/latest-request.ts");
  const requests = createLatestRequest();
  const old = requests.start();
  const latest = requests.start();
  assert.equal(old.signal.aborted, true);
  assert.equal(requests.isCurrent(old), false);
  assert.equal(requests.isCurrent(latest), true);
  requests.cancel();
  assert.equal(latest.signal.aborted, true);
  assert.equal(requests.isCurrent(latest), false);
});
