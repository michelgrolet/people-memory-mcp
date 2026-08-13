import { test } from "node:test";
import assert from "node:assert/strict";

import { buildFamilyTree, famNodeHtml, edgeKindLabel, setData, setById } from "./extract.mjs";

// "parent" is the only directed edge kind (a_id = parent, b_id = child); sibling/partner are
// symmetric and read from either side. Fixture below exercises two generations up and down,
// plus the "a parent's partner is probably the other parent" fold in buildFamilyTree.
const people = {
  1: { id: 1, name: "Alice", tie: 3 },
  2: { id: 2, name: "Bob", tie: 2 },     // father
  3: { id: 3, name: "Carol", tie: 2 },   // mother, linked to Bob only via partner, not parent
  4: { id: 4, name: "Dan", tie: 1 },     // paternal grandfather
  5: { id: 5, name: "Eve", tie: 1 },     // paternal grandmother
  6: { id: 6, name: "Frank", tie: 3 },   // sibling
  7: { id: 7, name: "Grace", tie: 4 },   // partner
  8: { id: 8, name: "Henry", tie: 3 },   // child
  9: { id: 9, name: "Ivy", tie: 1 },     // grandchild
  10: { id: 10, name: "Jack <script>", tie: 1 }, // isolated, and a name that must come out escaped
};

setData({
  edges: [
    { a: 2, b: 1, kind: "parent" },
    { a: 4, b: 2, kind: "parent" },
    { a: 5, b: 2, kind: "parent" },
    { a: 1, b: 8, kind: "parent" },
    { a: 8, b: 9, kind: "parent" },
    { a: 1, b: 6, kind: "sibling" },
    { a: 1, b: 7, kind: "partner" },
    { a: 2, b: 3, kind: "partner" }, // Bob's partner Carol — not a recorded parent of Alice
  ],
});
setById(new Map(Object.values(people).map(p => [p.id, p])));

test("walks two generations up and down from directed parent edges", () => {
  const fam = buildFamilyTree(1);
  const names = list => list.map(p => p.name).sort();
  assert.deepEqual(names(fam.parents), ["Bob", "Carol"]);
  assert.deepEqual(names(fam.grandparents), ["Dan", "Eve"]);
  assert.deepEqual(names(fam.siblings), ["Frank"]);
  assert.deepEqual(names(fam.partners), ["Grace"]);
  assert.deepEqual(names(fam.children), ["Henry"]);
  assert.deepEqual(names(fam.grandchildren), ["Ivy"]);
});

test("folds a recorded parent's partner into the parents row without a direct parent edge", () => {
  const fam = buildFamilyTree(1);
  assert.ok(fam.parents.some(p => p.name === "Carol"), "Carol reached Alice only via Bob's partner edge");
});

test("a person with no family edges returns empty rows, not a crash", () => {
  const fam = buildFamilyTree(10);
  assert.equal(fam.person.name, "Jack <script>");
  for (const key of ["grandparents", "parents", "siblings", "partners", "children", "grandchildren"]) {
    assert.deepEqual(fam[key], [], `${key} should be empty for an isolated person`);
  }
});

test("buildFamilyTree returns null for an unknown id instead of throwing", () => {
  assert.equal(buildFamilyTree(999), null);
});

test("edgeKindLabel reads direction off which side the current person is on", () => {
  assert.equal(edgeKindLabel({ kind: "parent", a: 2, b: 1 }, 1), "child of");
  assert.equal(edgeKindLabel({ kind: "parent", a: 2, b: 1 }, 2), "parent of");
  assert.equal(edgeKindLabel({ kind: "sibling", a: 1, b: 6 }, 1), "sibling");
});

test("famNodeHtml escapes the name and marks self as non-navigable", () => {
  const jack = people[10];
  const node = famNodeHtml(jack, false);
  assert.match(node, /data-fam-goto="10"/);
  assert.match(node, /Jack &lt;script&gt;/);
  assert.doesNotMatch(node, /<script>/);

  const self = famNodeHtml(people[1], true);
  assert.doesNotMatch(self, /data-fam-goto/);
  assert.match(self, /class="fam-node self"/);
});
