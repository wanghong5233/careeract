import assert from "node:assert/strict";
import test from "node:test";
import { loadSource } from "./load-source.mjs";

const review = loadSource("lib/material-review.ts");
const proposal = { id: "proposal", changes: [{ id: "first", state: "pending" }, { id: "second", state: "pending" }, { id: "third", state: "pending" }] };

test("unchecking the default selection preserves other pending blocks and reload excludes resolved blocks", () => {
  const selection = review.toggleSelection(proposal, undefined, "second", false);
  assert.deepEqual(selection, ["first", "third"]);
  assert.deepEqual(review.toggleSelection(proposal, selection, "second", true), ["first", "third", "second"]);
  const accepted = { ...proposal, changes: proposal.changes.map(change => change.id === "first" ? { ...change, state: "accepted" } : change) };
  assert.deepEqual(review.pendingSelection(accepted, selection), ["third"]);
  assert.deepEqual(review.pendingSelection(accepted), ["second", "third"]);
  assert.deepEqual(review.pendingSelection(accepted, []), []);
});

test("targeted feedback requests only one pending suggestion without approval or a whole replacement", () => {
  const prompt = review.rewritePrompt("material", proposal, "second");
  assert.match(prompt, /提议 proposal 中的 second/);
  assert.match(prompt, /review_version/);
  assert.match(prompt, /不要创建整份新提议或接受修改/);
  assert.match(prompt, /其他已接受、拒绝和待审内容必须保留/);
});
