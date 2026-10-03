import assert from "node:assert/strict";
import test from "node:test";
import { loadSource } from "./load-source.mjs";

function fixture() {
  const states = [];
  const effects = [];
  const calls = [];
  const events = new EventTarget();
  let slot = 0;
  let mounted = false;
  const source = loadSource("hooks/use-project-list.ts", {
    react: {
      useState(initial) {
        const index = slot++;
        if (!mounted) states[index] = typeof initial === "function" ? initial() : initial;
        return [states[index], value => {
          states[index] = typeof value === "function" ? value(states[index]) : value;
        }];
      },
      useCallback: callback => callback,
      useEffect: effect => { if (!mounted) effects.push(effect); },
    },
    "@/lib/latest-request": loadSource("lib/latest-request.ts"),
    "@/lib/projects": {
      readProjects: (query, signal) => new Promise((resolve, reject) => {
        calls.push({ query, signal, resolve, reject });
      }),
    },
  }, { window: events });
  function render() {
    slot = 0;
    return source.useProjectList();
  }
  render();
  mounted = true;
  const cleanups = effects.map(effect => effect());
  return {
    calls, render,
    refreshEvent: () => events.dispatchEvent(new Event("careeract:projects-changed")),
    unmount: () => cleanups.forEach(cleanup => cleanup?.()),
  };
}

const settle = () => new Promise(resolve => setImmediate(resolve));

test("project list hook keeps a new event refresh when the initial request resolves late", async () => {
  const view = fixture();
  view.refreshEvent();
  assert.equal(view.calls[0].signal.aborted, true);
  view.calls[1].resolve({ items: [{ id: "new" }], next_cursor: "next" });
  await settle();
  view.calls[0].resolve({ items: [{ id: "old" }], next_cursor: null });
  await settle();
  assert.deepEqual(view.render().projects, [{ id: "new" }]);
  assert.equal(view.render().cursor, "next");
  assert.equal(view.render().loading, false);
  view.unmount();
});

test("project list refresh supersedes pagination and stale failures cannot stop loading", async () => {
  const view = fixture();
  view.calls[0].resolve({ items: [{ id: "first" }], next_cursor: "page-two" });
  await settle();
  const more = view.render().loadMore();
  assert.equal(view.calls[1].query.cursor, "page-two");
  const refresh = view.render().refresh();
  view.calls[1].reject(new Error("stale page failed"));
  await more;
  assert.equal(view.render().loading, true);
  assert.equal(view.render().error, "");
  view.calls[2].resolve({ items: [{ id: "refreshed" }], next_cursor: null });
  await refresh;
  assert.deepEqual(view.render().projects, [{ id: "refreshed" }]);
  view.unmount();
});

test("project list local changes and unmount reject late data and remove the refresh listener", async () => {
  const view = fixture();
  view.render().updateProjects([{ id: "locally-created" }]);
  view.calls[0].resolve({ items: [], next_cursor: null });
  await settle();
  assert.deepEqual(view.render().projects, [{ id: "locally-created" }]);
  view.refreshEvent();
  view.unmount();
  assert.equal(view.calls[1].signal.aborted, true);
  view.calls[1].resolve({ items: [{ id: "after-unmount" }], next_cursor: null });
  await settle();
  view.refreshEvent();
  assert.equal(view.calls.length, 2);
  assert.deepEqual(view.render().projects, [{ id: "locally-created" }]);
});

test("project list pagination deduplicates records and current failures remain visible", async () => {
  const view = fixture();
  view.calls[0].resolve({ items: [{ id: "first" }], next_cursor: "page-two" });
  await settle();
  const more = view.render().loadMore();
  view.calls[1].resolve({ items: [{ id: "first" }, { id: "second" }], next_cursor: null });
  await more;
  assert.deepEqual(view.render().projects, [{ id: "first" }, { id: "second" }]);
  const refresh = view.render().refresh();
  view.calls[2].reject(new Error("current request failed"));
  await refresh;
  assert.equal(view.render().error, "current request failed");
  assert.equal(view.render().loading, false);
  view.unmount();
});
