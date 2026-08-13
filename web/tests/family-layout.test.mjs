import { test } from "node:test";
import assert from "node:assert/strict";

import { famLayout, TREE_ROW } from "./extract.mjs";

// The force graph can be wrong and still look fine — a spring is not a claim about anything.
// A row in the tree view IS a claim: everyone on it belongs to the same generation. So these
// tests are about the invariant, not the pixels: a child is exactly one row under its parent, a
// couple shares a row, and two people never land on the same spot.
const parent = (a, b) => ({ a, b, kind: "parent" });
const partner = (a, b) => ({ a, b, kind: "partner" });
const sibling = (a, b) => ({ a, b, kind: "sibling" });

test("a child sits exactly one row under its parent", () => {
  const pos = famLayout([parent(1, 2)]);
  assert.equal(pos.get(2).y - pos.get(1).y, TREE_ROW);
  assert.equal(pos.get(1).gen, 0);
  assert.equal(pos.get(2).gen, 1);
});

test("a grandchild lands two rows down, and the chain keeps its order", () => {
  const pos = famLayout([parent(1, 2), parent(2, 3)]);
  assert.equal(pos.get(3).y - pos.get(1).y, TREE_ROW * 2);
  assert.ok(pos.get(1).y < pos.get(2).y && pos.get(2).y < pos.get(3).y);
});

test("ten generations stay ten distinct rows", () => {
  const edges = [];
  for (let i = 1; i < 10; i++) edges.push(parent(i, i + 1));
  const pos = famLayout(edges);
  const gens = [...Array(10)].map((_, i) => pos.get(i + 1).gen);
  assert.deepEqual(gens, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
});

test("partners and siblings share a row and stay next to each other", () => {
  // 1 + 2 are a couple, 3 is their child, 4 is 3's sibling
  const pos = famLayout([partner(1, 2), parent(1, 3), parent(2, 3), parent(1, 4), sibling(3, 4)]);
  assert.equal(pos.get(1).y, pos.get(2).y, "a couple is one generation");
  assert.equal(pos.get(3).y, pos.get(4).y, "siblings are one generation");
  assert.equal(Math.abs(pos.get(1).x - pos.get(2).x), 76, "the couple is not split apart");
  assert.equal(pos.get(3).y - pos.get(1).y, TREE_ROW);
});

test("a parent's row wins over a partner's, so an in-law never floats a generation up", () => {
  // 3 marries into the family: 1 is 2's parent, 2 and 3 are partners
  const pos = famLayout([parent(1, 2), partner(2, 3)]);
  assert.equal(pos.get(2).y, pos.get(3).y);
  assert.equal(pos.get(2).y - pos.get(1).y, TREE_ROW);
});

test("two unrelated families are laid out without ever overlapping", () => {
  const pos = famLayout([
    parent(1, 2), parent(2, 3),
    parent(10, 11), parent(11, 12),
    partner(20, 21),
  ]);
  const seen = new Set();
  for (const [id, p] of pos) {
    const key = `${Math.round(p.x)}:${Math.round(p.y)}`;
    assert.ok(!seen.has(key), `${id} landed on top of somebody else at ${key}`);
    seen.add(key);
  }
  assert.equal(pos.size, 8);
});

test("only the three kinds that carry a generation place a person", () => {
  // "family" and "friend" are drawn on the graph but say nothing about who is older
  const pos = famLayout([parent(1, 2), { a: 2, b: 3, kind: "family" }, { a: 4, b: 5, kind: "friend" }]);
  assert.deepEqual([...pos.keys()].sort((x, y) => x - y), [1, 2]);
});

test("no family links at all returns an empty layout instead of throwing", () => {
  assert.equal(famLayout([]).size, 0);
  assert.equal(famLayout([{ a: 1, b: 2, kind: "colleague" }]).size, 0);
});

test("a self-referencing or circular parent link does not hang the page", () => {
  const pos = famLayout([parent(1, 1), parent(1, 2), parent(2, 3), parent(3, 1)]);
  assert.equal(pos.size, 3);
  for (const p of pos.values()) assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y));
});

test("a person recorded as their own parent's partner is placed, not dropped", () => {
  // real data has contradictions; the view has to survive them
  const pos = famLayout([parent(1, 2), partner(1, 2)]);
  assert.equal(pos.size, 2);
  for (const p of pos.values()) assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y));
});

test("the layout is centred on the origin, where the camera starts", () => {
  const edges = [];
  for (let i = 1; i < 30; i++) edges.push(parent(i, i + 1));
  const pos = famLayout(edges);
  const xs = [...pos.values()].map(p => p.x), ys = [...pos.values()].map(p => p.y);
  const mid = a => (Math.min(...a) + Math.max(...a)) / 2;
  assert.ok(Math.abs(mid(xs)) < 200, "horizontally centred");
  assert.ok(Math.abs(mid(ys)) < 200, "vertically centred");
});

test("a big tree stays fast enough to build on every toggle", () => {
  // his own imported tree is ~195 people over 10 generations; a binary pyramid of 500 is worse
  const edges = [];
  for (let i = 1; i <= 500; i++) { edges.push(parent(i, i * 2)); edges.push(parent(i, i * 2 + 1)); }
  const t0 = Date.now();
  const pos = famLayout(edges);
  assert.ok(pos.size > 900);
  assert.ok(Date.now() - t0 < 2000, "layout took too long to be run on a click");
});
