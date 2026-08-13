import { test } from "node:test";
import assert from "node:assert/strict";

import { bloodline, famLayout, TREE_ROW, TREE_COL } from "./extract.mjs";

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
  assert.ok(Math.abs(pos.get(1).x - pos.get(2).x) < TREE_COL * 2, "the couple is not split apart");
  assert.equal(pos.get(3).y - pos.get(1).y, TREE_ROW);
});

test("a spouse's own siblings never join yours in one run", () => {
  // Michel + his siblings, married to Solange who has siblings of her own. Merging partners into
  // the same group as siblings made the two families one unbroken row (2026-08-13).
  const pos = famLayout([
    sibling(1, 2), sibling(1, 3),          // his side
    partner(1, 10),                        // the marriage
    sibling(10, 11), sibling(10, 12),      // her side
  ]);
  const his = [1, 2, 3].map(i => pos.get(i).x), hers = [10, 11, 12].map(i => pos.get(i).x);
  assert.equal(new Set([...his, ...hers].map(x => pos.get(1).y)).size, 1, "still one generation");
  const gap = Math.min(...hers.map(h => Math.min(...his.map(x => Math.abs(h - x)))));
  assert.ok(Math.max(...his) < Math.min(...hers) || Math.max(...hers) < Math.min(...his),
    "the two families do not interleave");
  assert.ok(gap > 0, "and they are not the same block");
});

test("a spouse sits next to their own husband or wife, not at the end of the siblings", () => {
  // 1 is married to 10 and has four siblings. The edge list happens to put him in the middle of
  // them, which parked Solange four people away from Michel on the live graph (2026-08-13).
  const pos = famLayout([
    sibling(2, 1), sibling(3, 1), sibling(1, 4), sibling(1, 5), partner(1, 10),
  ]);
  assert.equal(pos.get(1).y, pos.get(10).y);
  assert.equal(Math.abs(pos.get(1).x - pos.get(10).x), TREE_COL, "the spouse is not in the next column along");
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

// ── bloodline: who is even on the page ─────────────────────────────────────────────────────────
// Scoping is the correctness question here, not the drawing: showing one person too many puts two
// unrelated families on the same rows, which is exactly the picture he rejected.

test("a spouse is drawn, their parents and siblings are not", () => {
  //  1 = root, 10 = the spouse, 11/12 = the spouse's siblings, 13 = the spouse's father
  const { ids, core } = bloodline([
    partner(1, 10), sibling(10, 11), sibling(10, 12), parent(13, 10),
  ], 1);
  assert.deepEqual([...ids].sort((a, b) => a - b), [1, 10]);
  assert.ok(core.has(1) && !core.has(10), "the spouse is a leaf, not blood");
});

test("every ancestor and every descendant comes in, over any number of generations", () => {
  const { ids } = bloodline([
    parent(1, 2), parent(2, 3), parent(3, 4),   // great-grandparent down to the root
    parent(4, 5), parent(5, 6),                 // and the root's own line down
  ], 4);
  assert.deepEqual([...ids].sort((a, b) => a - b), [1, 2, 3, 4, 5, 6]);
});

test("brothers and sisters are in, their children are not", () => {
  // 2 is the root's sibling, 20 is 2's child — a nephew is not on this tree
  const { ids } = bloodline([sibling(1, 2), parent(2, 20)], 1);
  assert.deepEqual([...ids].sort((a, b) => a - b), [1, 2]);
});

test("an uncle and a cousin never reach the page", () => {
  // 1 root, 2 root's father, 3 father's brother (uncle), 4 the uncle's child (cousin)
  const { ids } = bloodline([parent(2, 1), sibling(2, 3), parent(3, 4)], 1);
  assert.ok(!ids.has(3) && !ids.has(4), "the uncle's branch stays out");
  assert.deepEqual([...ids].sort((a, b) => a - b), [1, 2]);
});

test("two people who both married in are never linked to each other", () => {
  // 1 and 2 are siblings, 10 and 20 their respective spouses: 10 and 20 are strangers
  const edges = [sibling(1, 2), partner(1, 10), partner(2, 20)];
  const { ids, core } = bloodline(edges, 1);
  const drawn = edges.filter(e => ids.has(e.a) && ids.has(e.b) && (core.has(e.a) || core.has(e.b)));
  assert.equal(drawn.length, 3);
  assert.ok(!drawn.some(e => !core.has(e.a) && !core.has(e.b)));
});

test("no root, or a root with nothing recorded, does not throw", () => {
  assert.equal(bloodline([parent(1, 2)], null).ids.size, 0);
  assert.deepEqual([...bloodline([parent(1, 2)], 99).ids], [99]);
});

test("a person recorded as their own ancestor does not hang the page", () => {
  const { ids } = bloodline([parent(1, 2), parent(2, 3), parent(3, 1)], 1);
  assert.ok(ids.has(1) && ids.size <= 3);
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
