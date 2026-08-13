import test from "node:test";
import assert from "node:assert/strict";
import { personTag, pickPerson, setPeople } from "./extract.mjs";

// Synthetic people only, per AGENTS.md. The shape mirrors what `DATA.people` carries.
const PEOPLE = [
  { id: 1, name: "Wren Halloway", birthdate: "1901-03-04", org: null, city: "Ashford" },
  { id: 2, name: "Wren Halloway", birthdate: "1934-11-20", org: null, city: null },
  { id: 3, name: "Wren Halloway", birthdate: null, org: "Halloway & Sons", city: null },
  { id: 4, name: "Perrin Vasque", birthdate: "1962-07-01", org: null, city: null },
  { id: 5, name: "Orsen Kite", birthdate: null, org: null, city: null },
];

test("a unique name resolves to that person", () => {
  setPeople(PEOPLE);
  assert.equal(pickPerson("Perrin Vasque", 99).id, 4);
});

test("surrounding whitespace does not stop a match", () => {
  setPeople(PEOPLE);
  assert.equal(pickPerson("  Perrin Vasque  ", 99).id, 4);
});

test("a shared name refuses rather than picking the first match", () => {
  setPeople(PEOPLE);
  assert.throws(() => pickPerson("Wren Halloway", 99), /3 people are called Wren Halloway/);
});

test("the refusal names the candidates so the right one can be typed back", () => {
  setPeople(PEOPLE);
  assert.throws(() => pickPerson("Wren Halloway", 99), err => {
    assert.match(err.message, /#1/);
    assert.match(err.message, /#2/);
    assert.match(err.message, /#3/);
    return true;
  });
});

test("a tagged name resolves past the ambiguity", () => {
  setPeople(PEOPLE);
  assert.equal(pickPerson(personTag(PEOPLE[1]), 99).id, 2);
  assert.equal(pickPerson("Wren Halloway (1901-03-04) #1", 99).id, 1);
});

test("the tag falls back to organization, then to the bare name", () => {
  assert.equal(personTag(PEOPLE[2]), "Wren Halloway (Halloway & Sons) #3");
  assert.equal(personTag(PEOPLE[4]), "Orsen Kite #5");
});

// A name shared with the person whose drawer is open is not ambiguous: excluding them can leave
// exactly one candidate, and the link should just be written.
test("excluding the current person can settle an otherwise shared name", () => {
  setPeople(PEOPLE.filter(p => p.id !== 3));
  assert.equal(pickPerson("Wren Halloway", 1).id, 2);
});

test("an unknown name is refused", () => {
  setPeople(PEOPLE);
  assert.throws(() => pickPerson("Nobody At All", 99), /Person not found/);
});

test("an empty box is refused before anything is looked up", () => {
  setPeople(PEOPLE);
  assert.throws(() => pickPerson("   ", 99), /Type a person's name/);
  assert.throws(() => pickPerson(null, 99), /Type a person's name/);
});

test("a stale tag is refused instead of resolving to nobody", () => {
  setPeople(PEOPLE);
  assert.throws(() => pickPerson("Wren Halloway #404", 99), /no longer in the graph/);
});

test("linking a person to themselves is refused, tagged or not", () => {
  setPeople(PEOPLE);
  assert.throws(() => pickPerson("Perrin Vasque #4", 4), /the same person/);
  assert.throws(() => pickPerson("Perrin Vasque", 4), /Person not found/);
});
