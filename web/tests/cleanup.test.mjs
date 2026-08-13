import test from "node:test";
import assert from "node:assert/strict";
import { cleanFold, cleanOrgFold, cleanDomainFold, cleanTokensSubset, cleanScan, cleanItemActs, cleanBodyHtml, cleanConfirm } from "./extract.mjs";

// Synthetic people only, per AGENTS.md. The shape mirrors what `DATA` carries after `load()`.
const person = (id, name, extra = {}) => ({
  id, name, identifiers: [], facts: [], interactions: [], affiliations: [],
  org: null, role: null, city: null, birthdate: null, ...extra,
});
const scan = (data, skipped = new Set()) =>
  cleanScan({ people: [], orgs: [], edges: [], affs: [], ...data }, skipped);
const section = (res, id) => res.sections.find(s => s.id === id);
const keys = (res, id) => (section(res, id) ? section(res, id).items.map(i => i.key) : []);

test("folding a name ignores case, accents and punctuation", () => {
  assert.equal(cleanFold("Ambroise d’Ambel"), cleanFold("ambroise d'ambel"));
  assert.equal(cleanFold("Éloïse Vantard"), cleanFold("Eloise Vantard"));
  assert.notEqual(cleanFold("Eloise Vantard"), cleanFold("Heloise Vantard"));
});

test("an organization folds without its legal suffix, but never to nothing", () => {
  assert.equal(cleanOrgFold("Kite Freight Inc"), cleanOrgFold("kite-freight"));
  assert.equal(cleanOrgFold("Halloway & Sons SAS"), cleanOrgFold("halloway sons"));
  assert.notEqual(cleanOrgFold("Halloway & Sons"), cleanOrgFold("Halloway and Sons"),
    "a spelled-out word is a real difference, unlike punctuation");
  assert.equal(cleanOrgFold("Group"), "group", "a name made only of suffixes keeps them");
});

test("a domain folds past protocol, www and path", () => {
  assert.equal(cleanDomainFold("https://www.kite-freight.example/careers"), "kite-freight.example");
  assert.equal(cleanDomainFold(null), "");
});

test("token subset only accepts names that add words, never names that swap them", () => {
  assert.ok(cleanTokensSubset(["anne", "vantard"], ["anne", "marie", "vantard"]));
  assert.ok(!cleanTokensSubset(["anne", "claire", "vantard"], ["anne", "marie", "vantard"]));
});

test("the same email on two records is reported", () => {
  const res = scan({
    people: [
      person(1, "Ambroise Vantard", { identifiers: [{ kind: "email", value: "a@kite.example" }] }),
      person(2, "A. Vantard", { identifiers: [{ kind: "email", value: "A@Kite.Example" }] }),
    ],
  });
  assert.deepEqual(keys(res, "dup-ident"), ["ident:email|a@kite.example"]);
});

test("two records with the same name are reported once, as a pair", () => {
  const res = scan({ people: [person(1, "Ambroise Vantard"), person(2, "ambroise vantard")] });
  assert.deepEqual(keys(res, "dup-name"), ["name:1+2"]);
});

// The whole point of the screen: three sisters given the same name must not read as one person
// filed three times. A link between two records is somebody having already decided they differ.
test("same-name records already linked to each other are not duplicates", () => {
  const people = [person(1, "Marie Rouyer"), person(2, "Marie Rouyer"), person(3, "Marie Rouyer")];
  const edges = [
    { a: 1, b: 2, kind: "sibling" }, { a: 1, b: 3, kind: "sibling" }, { a: 2, b: 3, kind: "sibling" },
  ];
  assert.deepEqual(keys(scan({ people, edges }), "dup-name"), []);
});

test("a father and a son sharing a name are left alone once the parent link exists", () => {
  const people = [person(1, "Jean Raillere"), person(2, "Jean Raillere")];
  assert.deepEqual(keys(scan({ people, edges: [{ a: 1, b: 2, kind: "parent" }] }), "dup-name"), []);
});

test("a spelled-out middle name is a near match, a different middle name is not", () => {
  const near = scan({ people: [person(1, "Anne Vantard"), person(2, "Anne Marie Vantard")] });
  assert.deepEqual(keys(near, "dup-near"), ["near:1+2"]);
  const distinct = scan({ people: [person(1, "Jean Claire Vantard"), person(2, "Jean Marie Vantard")] });
  assert.deepEqual(keys(distinct, "dup-near"), []);
});

// A LinkedIn export carries display names made of emoji, which fold to an empty first or last
// token. Every such name would otherwise match every other one.
test("a name whose words fold to nothing never matches another", () => {
  const res = scan({ people: [person(1, "🍃 Yoo N 🔋"), person(2, "✨ Kite R 🚀")] });
  assert.deepEqual(keys(res, "dup-near"), []);
  assert.deepEqual(keys(res, "dup-name"), []);
});

test("organizations match on folded name or domain, but not a declared parent and subsidiary", () => {
  const orgs = [
    { id: 10, name: "Kite Freight", domain: null, parent_org_id: null },
    { id: 11, name: "kite-freight inc", domain: null, parent_org_id: null },
    { id: 12, name: "Kite Freight Belgium", domain: null, parent_org_id: 10 },
    { id: 13, name: "Halloway", domain: "https://www.halloway.example", parent_org_id: null },
    { id: 14, name: "Halloway & Sons", domain: "halloway.example", parent_org_id: null },
  ];
  const affs = orgs.map(o => ({ org_id: o.id, person_id: 1 }));
  assert.deepEqual(keys(scan({ orgs, affs, people: [person(1, "Ambroise Vantard")] }), "dup-org"),
    ["org:10+11", "org:13+14"]);
});

test("an organization with no member and no subsidiary is reported, one with either is not", () => {
  const orgs = [
    { id: 10, name: "Kite Freight", domain: null, parent_org_id: null },
    { id: 11, name: "Halloway", domain: null, parent_org_id: null },
    { id: 12, name: "Halloway Belgium", domain: null, parent_org_id: 11 },
    { id: 13, name: "Vantard Studio", domain: null, parent_org_id: null },
  ];
  const res = scan({ orgs, affs: [{ org_id: 13, person_id: 1 }], people: [person(1, "Ambroise Vantard")] });
  assert.deepEqual(keys(res, "org-empty"), ["orgempty:10", "orgempty:12"]);
});

test("a link to oneself, a doubled link and a parent who is also a sibling are all reported", () => {
  const people = [person(1, "Ambroise Vantard"), person(2, "Eloise Vantard")];
  const edges = [
    { a: 1, b: 1, kind: "friend" },
    { a: 1, b: 2, kind: "colleague" }, { a: 2, b: 1, kind: "colleague" },
    { a: 1, b: 2, kind: "parent" }, { a: 1, b: 2, kind: "sibling" },
  ];
  const found = keys(scan({ people, edges }), "link-broken");
  assert.ok(found.includes("self:1:friend"));
  assert.ok(found.includes("dupedge:1+2|colleague"));
  assert.ok(found.includes("clash:1+2"));
});

test("a parent barely older than their child is reported, a plausible one is not", () => {
  const edges = [{ a: 1, b: 2, kind: "parent" }, { a: 3, b: 4, kind: "parent" }];
  const people = [
    person(1, "Ambroise Vantard", { birthdate: "1990-04-02" }),
    person(2, "Eloise Vantard", { birthdate: "1998-01-09" }),
    person(3, "Hilaire Rouyer", { birthdate: "1960-06-01" }),
    person(4, "Marin Rouyer", { birthdate: "1991-02-20" }),
  ];
  assert.deepEqual(keys(scan({ people, edges }), "link-broken"), ["gap:1+2"]);
});

test("a parent link pointing the wrong way, making someone their own ancestor, is caught", () => {
  const people = [person(1, "Ambroise Vantard"), person(2, "Eloise Vantard"), person(3, "Marin Vantard")];
  const edges = [
    { a: 1, b: 2, kind: "parent" }, { a: 2, b: 3, kind: "parent" }, { a: 3, b: 1, kind: "parent" },
  ];
  const found = keys(scan({ people, edges }), "link-broken");
  assert.equal(found.length, 1);
  assert.match(found[0], /^cycle:1\+2\+3$/);
});

test("a plain family tree raises nothing", () => {
  const people = [
    person(1, "Ambroise Vantard", { birthdate: "1962-03-04" }),
    person(2, "Eloise Vantard", { birthdate: "1990-07-08" }),
  ];
  const res = scan({ people, edges: [{ a: 1, b: 2, kind: "parent" }] });
  assert.equal(res.total, 0);
});

test("an unclassified family link is listed with its note", () => {
  const people = [person(1, "Ambroise Vantard"), person(2, "Eloise Vantard")];
  const res = scan({ people, edges: [{ a: 1, b: 2, kind: "family", note: "aunt, to confirm" }] });
  assert.deepEqual(keys(res, "link-vague"), ["vague:1+2"]);
  assert.match(section(res, "link-vague").items[0].headline, /aunt, to confirm/);
});

// A note is written by a human and lands in the page as HTML, exactly like a person's name.
test("a note and a name are escaped before they reach the page", () => {
  const people = [person(1, "<img src=x onerror=alert(1)>"), person(2, "Eloise Vantard")];
  const res = scan({ people, edges: [{ a: 1, b: 2, kind: "family", note: "<script>alert(1)</script>" }] });
  const item = section(res, "link-vague").items[0];
  assert.ok(!item.headline.includes("<script>"));
  assert.equal(item.refs[0].name, "<img src=x onerror=alert(1)>", "the name is escaped where it is rendered, not here");
});

test("a skipped key disappears and is counted, and skipping one does not hide another", () => {
  const people = [person(1, "Ambroise Vantard"), person(2, "ambroise vantard"), person(3, "Eloise Rouyer"), person(4, "eloise rouyer")];
  const before = scan({ people });
  assert.equal(before.total, 2);
  const after = scan({ people }, new Set(["name:1+2"]));
  assert.deepEqual(keys(after, "dup-name"), ["name:3+4"]);
  assert.equal(after.total, 1);
  assert.equal(after.skipped, 1);
});

test("an empty graph scans clean rather than throwing", () => {
  assert.equal(scan({}).total, 0);
});

// ── the repairs the screen offers ────────────────────────────────────────────
// Everything below is about what a click is going to do to the graph. A button that names the
// wrong record, or points a parent link the wrong way, does its damage silently.

const acts = item => (item.acts || []).map(a => a.label);
const actOf = (item, label) => (item.acts || []).find(a => a.label === label);

test("every kind of duplicate offers to keep one record and fold the rest in", () => {
  const people = [
    person(1, "Ambroise Vantard", { identifiers: [{ kind: "email", value: "a@vantard.example" }] }),
    person(2, "A. Vantard", { identifiers: [{ kind: "email", value: "a@vantard.example" }] }),
    person(3, "Eloise Rouyer"), person(4, "eloise rouyer"),
    person(5, "Marc Halloway"), person(6, "Marc Julien Halloway"),
  ];
  const res = scan({ people });
  for (const id of ["dup-ident", "dup-name", "dup-near"])
    assert.ok(section(res, id).items.every(i => i.merge === "person"), `${id} is repairable`);
});

test("two organizations matched as one offer the same, and an empty one offers deletion", () => {
  const orgs = [{ id: 1, name: "Kite Freight" }, { id: 2, name: "Kite Freight Inc" }];
  const res = scan({ orgs });
  assert.equal(section(res, "dup-org").items[0].merge, "org");
  const empty = section(res, "org-empty").items;
  assert.equal(empty.length, 2);
  assert.deepEqual(acts(empty[0]), ["Delete it"]);
  // The confirmation names the organization, so it has to travel with the action, not be looked up.
  assert.equal(actOf(empty[0], "Delete it").name, "Kite Freight");
});

test("deleting an empty organization is confirmed by name before it runs", () => {
  const ask = cleanConfirm({ op: "do", name: "Kite Freight" });
  assert.equal(ask.go, "Delete");
  assert.match(ask.text, /Kite Freight/);
  assert.match(ask.text, /recoverable/);
  assert.ok(!cleanConfirm({ op: "do", name: "<img src=x>" }).text.includes("<img"));
});

test("retyping a link and deleting one run on the click, without a confirmation", () => {
  assert.equal(cleanConfirm({ op: "ek", kind: "sibling" }), null);
  assert.equal(cleanConfirm({ op: "ed", kind: "family" }), null);
});

// A duplicate gets one button, not a decision per card: which record survives, and what it ends
// up holding, is answered in the merge window.
test("a duplicate is one Merge button carrying both records", () => {
  const people = [person(1, "Ambroise Vantard"), person(2, "ambroise vantard")];
  const item = section(scan({ people }), "dup-name").items[0];
  const list = cleanItemActs(item);
  assert.deepEqual(list.map(a => a.label), ["Merge"]);
  assert.deepEqual([list[0].op, list[0].type, list[0].ids], ["mg", "person", [1, 2]]);
});

test("Merge comes first, ahead of the repairs a finding already carried", () => {
  const orgs = [{ id: 1, name: "Kite Freight" }, { id: 2, name: "Kite Freight Inc" }];
  const res = scan({ orgs });
  assert.deepEqual(cleanItemActs(section(res, "dup-org").items[0]).map(a => a.label), ["Merge"]);
  assert.deepEqual(cleanItemActs(section(res, "org-empty").items[0]).map(a => a.label), ["Delete it"]);
});

test("a finding with three records hands all three on, for the window to take two at a time", () => {
  const ident = [{ kind: "email", value: "a@vantard.example" }];
  const people = [1, 2, 3].map(i => person(i, `Person ${i}`, { identifiers: ident }));
  const item = section(scan({ people }), "dup-ident").items[0];
  assert.deepEqual(cleanItemActs(item)[0].ids, [1, 2, 3]);
});

test("no repair button is offered while a row is asking to be confirmed", () => {
  const orgs = [{ id: 1, name: "Kite Freight" }];
  const res = scan({ orgs });
  const key = section(res, "org-empty").items[0].key;
  assert.ok(cleanBodyHtml(res, null).includes("Delete it"));
  const asking = cleanBodyHtml(res, { key, text: "Sure?", go: "Delete" });
  assert.ok(asking.includes("cl-confirm"));
  assert.ok(!asking.includes("Delete it"), "no second repair can be started under an open question");
});

test("a confirmation on one row leaves the other rows usable", () => {
  const orgs = [{ id: 1, name: "Kite Freight" }, { id: 2, name: "Halloway" }];
  const res = scan({ orgs });
  const key = section(res, "org-empty").items[0].key;
  assert.equal((cleanBodyHtml(res, { key, text: "Sure?", go: "Delete" }).match(/>Delete it</g) || []).length, 1);
});

test("an action survives the round trip through the attribute it is written into", () => {
  const orgs = [{ id: 1, name: 'The "Kite" Freight Co' }];
  const html = cleanBodyHtml(scan({ orgs }), null);
  const raw = html.match(/data-clean-act="([^"]*)"/)[1];
  const act = JSON.parse(raw.replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&"));
  assert.equal(act.op, "do");
  assert.equal(act.name, 'The "Kite" Freight Co');
  assert.equal(act.item, "orgempty:1");
});
