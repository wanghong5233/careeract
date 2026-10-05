import assert from "node:assert/strict";
import test from "node:test";
import { loadSource } from "./load-source.mjs";

const settle = () => new Promise(resolve => setImmediate(resolve));

function hooksFixture(source, dependencies, globals = {}) {
  const slots = [];
  const queuedEffects = [];
  let slot = 0;
  function changed(previous, next) { return !previous || next.some((value, index) => value !== previous[index]); }
  const hooks = {
    useState(initial) {
      const index = slot++;
      if (!slots[index]) slots[index] = { value: typeof initial === "function" ? initial() : initial };
      return [slots[index].value, value => { slots[index].value = typeof value === "function" ? value(slots[index].value) : value; }];
    },
    useCallback(callback, deps) {
      const index = slot++;
      if (changed(slots[index]?.deps, deps)) slots[index] = { value: callback, deps };
      return slots[index].value;
    },
    useEffect(effect, deps) {
      const index = slot++;
      if (changed(slots[index]?.deps, deps)) {
        queuedEffects.push(() => { slots[index]?.cleanup?.(); slots[index] = { deps, cleanup: effect() }; });
      }
    },
  };
  const loaded = loadSource(source, { react: hooks, "@/lib/latest-request": loadSource("lib/latest-request.ts"), "@/lib/agent-runtime": loadSource("lib/agent-runtime.ts"), ...dependencies }, globals);
  return {
    render(name, ...args) {
      slot = 0;
      const result = loaded[name](...args);
      queuedEffects.splice(0).forEach(effect => effect());
      return result;
    },
    unmount() { slots.forEach(item => item?.cleanup?.()); },
  };
}

function spaceFixture() {
  const values = new Map();
  return loadSource("lib/agent-space-state.ts", {}, {
    window: {},
    sessionStorage: { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) },
  });
}

const remote = (id, version = "v1") => ({ session_id: id, title: "合成对话", project_id: null, archived: false, version });

test("server conversation metadata replaces local metadata while drafts and per-tab views survive", () => {
  const { newSpaceConversation, mergeSpaceConversations } = spaceFixture();
  const local = { ...newSpaceConversation("one", "old"), draft: "未发送", title: "旧名称", tabs: [{ href: "/workspace/background", label: "背景" }], activeHref: "/workspace/background", panelHidden: true };
  const state = { conversations: [local], selectedId: "one", navigation: true, panelWidth: 40 };
  const result = mergeSpaceConversations(state, [{ ...remote("one"), archived: true }]);
  assert.equal(result.conversations[0].projectId, null);
  assert.equal(result.conversations[0].archived, true);
  assert.equal(result.conversations[0].draft, "未发送");
  assert.deepEqual(result.conversations[0].tabs, local.tabs);
  assert.equal(result.conversations[0].activeHref, local.activeHref);
  assert.equal(result.selectedId, "one");
  assert.equal(state.conversations[0].title, "旧名称");
});

test("directory hook rejects stale refreshes after writes and preserves unsent input when assigning server ID", async () => {
  const space = spaceFixture();
  const store = space.getSpaceStore("owner");
  store.snapshot();
  store.update(state => ({ ...state, conversations: [{ ...state.conversations[0], draft: "合成未发送草稿" }] }));
  const calls = [];
  const writes = [];
  const events = new EventTarget();
  const view = hooksFixture("hooks/use-agent-conversations.ts", {
    "@/lib/agent-space-state": space,
    "@/lib/agent-conversations": {
      readConversations: (cursor, signal) => new Promise((resolve, reject) => calls.push({ cursor, signal, resolve, reject })),
      createConversation: async id => { writes.push(id); return remote(`conversation:${id}`); },
      saveConversation: async (id, version, changes) => ({ ...remote(id, "v2"), ...changes }),
    },
  }, { window: events });
  const render = () => view.render("useAgentConversations", "owner");
  render();
  events.dispatchEvent(new Event("focus"));
  calls[1].resolve({ items: [remote("old")], next_cursor: null });
  await settle();
  calls[0].resolve({ items: [remote("late")], next_cursor: null });
  await settle();
  assert.ok(!store.snapshot().conversations.some(item => item.id === "late"));
  const refresh = render().refresh();
  const saved = await render().persist("new");
  assert.equal(store.snapshot().selectedId, saved.session_id);
  assert.equal(store.snapshot().conversations.find(item => item.id === saved.session_id).draft, "合成未发送草稿");
  calls[2].resolve({ items: [{ ...saved, title: "过时名称" }], next_cursor: null });
  await refresh;
  assert.equal(store.snapshot().conversations.find(item => item.id === saved.session_id).title, "合成对话");
  assert.equal(writes.length, 1);
  view.unmount();
});

test("failed conversation creation retains a stable retry ID and never promotes the draft to a message", async () => {
  const space = spaceFixture();
  const store = space.getSpaceStore("owner");
  store.snapshot();
  const identifiers = [];
  const view = hooksFixture("hooks/use-agent-conversations.ts", {
    "@/lib/agent-space-state": space,
    "@/lib/agent-conversations": {
      readConversations: async () => ({ items: [], next_cursor: null }),
      createConversation: async id => { identifiers.push(id); throw new Error("unknown result"); },
    },
  }, { window: new EventTarget() });
  const render = () => view.render("useAgentConversations", "owner");
  await assert.rejects(render().persist("new"), /unknown result/);
  await assert.rejects(render().persist("new"), /unknown result/);
  assert.equal(identifiers[0], identifiers[1]);
  assert.equal(store.snapshot().selectedId, "new");
  assert.equal(store.snapshot().conversations[0].version, undefined);
  view.unmount();
});

test("history hook cancels old reads and never displays the previous conversation during switching", async () => {
  const calls = [];
  const view = hooksFixture("hooks/use-conversation-history.ts", {
    "@/lib/agent-conversations": { readConversationHistory: (id, signal) => new Promise((resolve, reject) => calls.push({ id, signal, resolve, reject })) },
  }, { window: new EventTarget() });
  const first = view.render("useConversationHistory", "first", true);
  assert.equal(first.loading, true);
  await settle();
  calls[0].resolve({ session: remote("first"), messages: [{ id: "first-message" }] });
  await settle();
  assert.equal(view.render("useConversationHistory", "first", true).history.messages[0].id, "first-message");
  const changed = view.render("useConversationHistory", "second", true);
  assert.equal(changed.history, null);
  assert.equal(changed.loading, true);
  assert.equal(calls[0].signal.aborted, true);
  await settle();
  calls[1].reject(new Error("history unavailable"));
  await settle();
  const failed = view.render("useConversationHistory", "second", true);
  assert.equal(failed.history, null);
  assert.equal(failed.error, "history unavailable");
  const retry = failed.refresh();
  const local = view.render("useConversationHistory", "local-draft", false);
  assert.equal(local.loading, false);
  assert.equal(local.history, null);
  calls[2].resolve({ session: remote("second"), messages: [{ id: "stale-retry" }] });
  await retry;
  assert.equal(view.render("useConversationHistory", "local-draft", false).history, null);
  view.unmount();
});

test("history hook restores and polls a server run without replaying input", async () => {
  const events = new EventTarget();
  const timers = new Map();
  const calls = [];
  const view = hooksFixture("hooks/use-conversation-history.ts", {
    "@/lib/agent-conversations": { readConversationHistory: (id, signal) => new Promise(resolve => calls.push({ id, signal, resolve })) },
  }, { window: events, setInterval: callback => { timers.set(1, callback); return 1; }, clearInterval: id => timers.delete(id) });
  const render = () => view.render("useConversationHistory", "restored", true);
  render();
  await settle();
  calls[0].resolve({ session: remote("restored"), messages: [], runs: [{ run_id: "accepted", status: "RUNNING" }] });
  await settle();
  assert.deepEqual(render().activeRun, { run_id: "accepted", status: "RUNNING" });
  assert.equal(timers.size, 1);
  timers.get(1)();
  calls[1].resolve({ session: remote("restored"), messages: [{ id: "saved", run_status: "CANCELLED" }], runs: [{ run_id: "accepted", status: "CANCELLED" }] });
  await settle();
  assert.equal(render().activeRun, null);
  assert.equal(render().history.messages[0].run_status, "CANCELLED");
  assert.equal(timers.size, 0);
  assert.equal(calls.length, 2);
  view.unmount();
});

test("automatic naming only follows saved completed input and late title responses cannot replace another conversation", async () => {
  const events = new EventTarget();
  const names = [];
  const view = hooksFixture("hooks/use-conversation-history.ts", {
    "@/lib/agent-conversations": {
      readConversationHistory: async id => ({ session: { ...remote(id), title_origin: id === "manual" ? "manual" : "default", title_generation_attempted: false }, messages: [{ role: "user", content: "合成目标", run_status: "COMPLETED" }] }),
      generateConversationTitle: (session, signal) => new Promise(resolve => names.push({ session, signal, resolve })),
    },
  }, { window: events });
  view.render("useConversationHistory", "first", true);
  await settle();
  assert.equal(view.render("useConversationHistory", "first", true).history.session.title, "合成对话");
  assert.equal(names.length, 1);
  view.render("useConversationHistory", "manual", true);
  await settle();
  assert.equal(names[0].signal.aborted, true);
  names[0].resolve({ ...remote("first", "v2"), title: "过期生成名称", title_origin: "generated", title_generation_attempted: true });
  await settle();
  assert.equal(view.render("useConversationHistory", "manual", true).history.session.session_id, "manual");
  assert.equal(names.length, 1);
  view.unmount();
});
