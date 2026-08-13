import test from "node:test";
import assert from "node:assert/strict";
import { orgTag, pickOrg, setOrgs } from "./extract.mjs";

// Synthetic orgs only, per AGENTS.md. The shape mirrors what `DATA.orgs` carries.
const ORGS = [
  { id: 10, name: "Halloway & Sons", domain: "halloway.example", city: null },
  { id: 11, name: "Halloway & Sons", domain: null, city: "Ashford" },
  { id: 12, name: "Kite Freight", domain: null, city: null },
];

test("a unique name resolves to that org", () => {
  setOrgs(ORGS);
  assert.equal(pickOrg("Kite Freight").id, 12);
});

test("the match is case-insensitive, matching the old lookup", () => {
  setOrgs(ORGS);
  assert.equal(pickOrg("kite freight").id, 12);
});

test("surrounding whitespace does not stop a match", () => {
  setOrgs(ORGS);
  assert.equal(pickOrg("  Kite Freight  ").id, 12);
});

test("a shared name refuses rather than picking the first match", () => {
  setOrgs(ORGS);
  assert.throws(() => pickOrg("Halloway & Sons"), /2 organizations are called Halloway & Sons/);
});

test("the refusal names the candidates so the right one can be typed back", () => {
  setOrgs(ORGS);
  assert.throws(() => pickOrg("Halloway & Sons"), err => {
    assert.match(err.message, /#10/);
    assert.match(err.message, /#11/);
    return true;
  });
});

test("a tagged name resolves past the ambiguity", () => {
  setOrgs(ORGS);
  assert.equal(pickOrg(orgTag(ORGS[1])).id, 11);
  assert.equal(pickOrg("Halloway & Sons (halloway.example) #10").id, 10);
});

test("the tag falls back to city, then to the bare name", () => {
  assert.equal(orgTag(ORGS[1]), "Halloway & Sons (Ashford) #11");
  assert.equal(orgTag(ORGS[2]), "Kite Freight #12");
});

test("an unknown name returns null, not an error", () => {
  setOrgs(ORGS);
  assert.equal(pickOrg("Nobody's Company"), null);
});

test("an empty box returns null before anything is looked up", () => {
  setOrgs(ORGS);
  assert.equal(pickOrg("   "), null);
  assert.equal(pickOrg(null), null);
});

test("a stale tag is refused instead of resolving to nothing", () => {
  setOrgs(ORGS);
  assert.throws(() => pickOrg("Halloway & Sons #404"), /no longer in the graph/);
});
