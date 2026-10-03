import assert from "node:assert/strict";
import test from "node:test";
import { loadSource } from "./load-source.mjs";

function fixture(dirty = true) {
  const windowEvents = new Map();
  const documentEvents = new Map();
  const navigated = [];
  let cleanup;
  class Element {}
  class HTMLAnchorElement extends Element {
    constructor(href, capability = false) { super(); this.href = href; this.capability = capability; this.target = ""; }
    closest(selector) { return selector === "a[href]" ? this : this.capability ? this : null; }
    hasAttribute() { return false; }
  }
  const guardModule = loadSource("hooks/use-draft-guard.ts", {
    react: { useEffect: effect => { cleanup = effect(); } },
    "@/components/workspace-actions": { useWorkspaceActions: () => ({ openContent: href => navigated.push(href) }) },
  }, {
    Element, HTMLAnchorElement,
    window: { location: new URL("https://careeract.example/workspace/background"), addEventListener: (name, handler) => windowEvents.set(name, handler), removeEventListener: name => windowEvents.delete(name) },
    document: { addEventListener: (name, handler) => documentEvents.set(name, handler), removeEventListener: name => documentEvents.delete(name) },
  });
  function DraftGuardFixture() {
    guardModule.useDraftGuard(dirty);
  }
  DraftGuardFixture();
  function click(href, options = {}, capability = false) {
    let prevented = false;
    let stopped = false;
    documentEvents.get("click")?.({ target: new HTMLAnchorElement(href, capability), button: 0, ...options, preventDefault: () => { prevented = true; }, stopPropagation: () => { stopped = true; } });
    return { prevented, stopped };
  }
  return { windowEvents, documentEvents, navigated, click, cleanup };
}

test("dirty navigation uses the shell confirmation path and cleans listeners on unmount", () => {
  const guard = fixture();
  assert.deepEqual(guard.click("https://careeract.example/workspace/projects"), { prevented: true, stopped: true });
  assert.deepEqual(guard.navigated, ["/workspace/projects"]);
  for (const name of ["beforeunload", "careeract:before-navigate"]) {
    let prevented = false;
    guard.windowEvents.get(name)({ preventDefault: () => { prevented = true; } });
    assert.equal(prevented, true);
  }
  guard.cleanup();
  assert.equal(guard.windowEvents.size, 0);
  assert.equal(guard.documentEvents.size, 0);
});

test("modified, external, same-page and capability clicks retain their dedicated handlers", () => {
  const guard = fixture();
  for (const options of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }]) {
    assert.equal(guard.click("https://careeract.example/workspace/projects", options).prevented, false);
  }
  assert.equal(guard.click("https://other.example/").prevented, false);
  assert.equal(guard.click("https://careeract.example/workspace/background#education").prevented, false);
  assert.equal(guard.click("https://careeract.example/workspace/projects", {}, true).prevented, false);
  assert.deepEqual(guard.navigated, []);
});

test("clean editor does not install blocking listeners", () => {
  const guard = fixture(false);
  assert.equal(guard.documentEvents.size, 0);
  assert.equal(guard.windowEvents.size, 0);
});
