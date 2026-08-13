import test from "node:test";
import assert from "node:assert/strict";
import {
  MERGE_FIELDS_PERSON, MERGE_FIELDS_ORG, mergeFields, mergeProposal, mergeWeight,
  mergeInvalid, mergeBodyHtml,
} from "./extract.mjs";

// The middle column is what the record becomes. If it shows something other than what the server
// would do, the window is lying about the merge it is offering — and the losing record is gone by
// the time anybody notices. Synthetic people only, per AGENTS.md.
const person = (id, name, extra = {}) => ({
  id, name, facts: [], interactions: [], identifiers: [], affiliations: [],
  birthdate: null, city: null, country: null, org: null, role: null,
  linkedinUrl: null, metWhere: null, metWhen: null, tie: null, summary: null, ...extra,
});
const P = MERGE_FIELDS_PERSON;

test("what one record lacks it takes from the other", () => {
  const keep = person(1, "Ambroise Vantard", { city: "Metz" });
  const drop = person(2, "A. Vantard", { city: null, role: "Luthier", birthdate: "1978-03-04" });
  const out = mergeProposal(P, keep, drop);
  assert.equal(out.name, "Ambroise Vantard", "the survivor's own value is never overwritten");
  assert.equal(out.city, "Metz");
  assert.equal(out.role, "Luthier");
  assert.equal(out.birthdate, "1978-03-04");
});

test("where both hold a value, the survivor's wins", () => {
  const keep = person(1, "Ambroise Vantard", { city: "Metz" });
  const drop = person(2, "Ambroise Vantard", { city: "Nancy" });
  assert.equal(mergeProposal(P, keep, drop).city, "Metz");
});

// Losing a line somebody wrote by hand is the one outcome a merge must not have.
test("two notes are kept one after the other, and one repeated note stays single", () => {
  const both = mergeProposal(P, person(1, "A", { summary: "Met at the wedding." }),
    person(2, "A", { summary: "Sister of Paul." }));
  assert.equal(both.summary, "Met at the wedding.\n\nSister of Paul.");

  const same = mergeProposal(P, person(1, "A", { summary: "Met at the wedding." }),
    person(2, "A", { summary: "  Met at the wedding.  " }));
  assert.equal(same.summary, "Met at the wedding.");

  const one = mergeProposal(P, person(1, "A"), person(2, "A", { summary: "Sister of Paul." }));
  assert.equal(one.summary, "Sister of Paul.");
});

test("the closer of the two ratings is the one that was observed", () => {
  assert.equal(mergeProposal(P, person(1, "A", { tie: 1 }), person(2, "A", { tie: 4 })).tie, "4");
  assert.equal(mergeProposal(P, person(1, "A", { tie: 3 }), person(2, "A")).tie, "3");
  assert.equal(mergeProposal(P, person(1, "A"), person(2, "A")).tie, "", "no rating stays no rating");
});

test("an organization merges on its own fields, not a person's", () => {
  const out = mergeProposal(mergeFields("org"),
    { id: 1, name: "Kite Freight", domain: null, note: "the real one" },
    { id: 2, name: "Kite Freight Inc", domain: "kite-freight.example", note: "the import's copy" });
  assert.equal(out.name, "Kite Freight");
  assert.equal(out.domain, "kite-freight.example");
  assert.equal(out.note, "the real one\n\nthe import's copy");
  assert.equal(mergeFields("org"), MERGE_FIELDS_ORG);
});

test("the fuller record is the one that survives by default", () => {
  const thin = person(1, "A", { facts: [{}] });
  const fat = person(2, "A", { facts: [{}, {}], interactions: [{}], identifiers: [{}] });
  assert.ok(mergeWeight(fat, 3) > mergeWeight(thin, 0));
  assert.ok(mergeWeight(person(1, "A"), 4) > mergeWeight(person(2, "A", { facts: [{}, {}, {}] }), 0),
    "a link counts for more than a fact: it is what other records point at");
});

// Refused before the merge, never after: by then the other record no longer exists to go back to.
test("a value that Postgres would refuse stops the merge instead of following it", () => {
  const ok = mergeProposal(P, person(1, "Ambroise Vantard"), person(2, "A"));
  assert.equal(mergeInvalid(P, ok), null);

  assert.match(mergeInvalid(P, { ...ok, name: "   " }), /Name cannot be empty/);
  assert.match(mergeInvalid(P, { ...ok, birthdate: "1978" }), /YYYY-MM-DD/);
  assert.equal(mergeInvalid(P, { ...ok, birthdate: "" }), null, "an empty date is a fine answer");
  assert.match(mergeInvalid(P, { ...ok, tie: "9" }), /1 to 5/);
  assert.match(mergeInvalid(P, { ...ok, tie: "2.5" }), /whole number/);
  assert.equal(mergeInvalid(P, { ...ok, tie: "3" }), null);
});

const state = (over = {}) => {
  const left = person(1, "Ambroise Vantard", { city: "Metz", counts: "3 links" });
  const right = person(2, "A. Vantard", { role: "Luthier", counts: "1 link" });
  return {
    type: "person", left, right, keep: left, drop: right, touched: [], rest: 0,
    extra: "4 links and every contact detail on either side.",
    values: mergeProposal(P, left, right), ...over,
  };
};

test("the window shows both records and the one they become", () => {
  const html = mergeBodyHtml(state());
  assert.equal((html.match(/class="mg-side"/g) || []).length, 2);
  assert.equal((html.match(/class="mg-mid"/g) || []).length, 1);
  assert.ok(html.includes("Ambroise Vantard"));
  assert.ok(html.includes("A. Vantard"));
  assert.equal((html.match(/data-mg-field=/g) || []).length, P.length, "every field is editable");
});

test("only the record that is not surviving offers to", () => {
  const html = mergeBodyHtml(state());
  assert.equal((html.match(/data-mg-keep="1"[^>]*disabled/g) || []).length, 1);
  assert.ok(html.includes('data-mg-keep="2"'));
  assert.ok(!/data-mg-keep="2"[^>]*disabled/.test(html));
});

// Clicking a value that already won would do nothing, and a row of dead buttons reads as broken.
test("a value is clickable only where taking it would change the result", () => {
  const html = mergeBodyHtml(state());
  assert.ok(!html.includes('data-mg-take="left|city"'), "the survivor's city already won");
  assert.ok(html.includes('data-mg-take="right|name"'), "the name that lost can still be taken");
  assert.ok(!html.includes('data-mg-take="right|city"'), "an empty value is nothing to take");
});

test("a field he typed into is marked as his, not as the proposal's", () => {
  assert.ok(!mergeBodyHtml(state()).includes("mg-row edited"));
  assert.ok(mergeBodyHtml(state({ touched: ["city"] })).includes("mg-row edited"));
});

test("a name typed by a human is escaped everywhere the window prints it", () => {
  const left = person(1, "<img src=x onerror=alert(1)>", { counts: "0 links" });
  const right = person(2, "</textarea><script>alert(1)</script>", { counts: "0 links" });
  const html = mergeBodyHtml({
    type: "person", left, right, keep: left, drop: right, touched: [], rest: 0,
    extra: "<script>alert(1)</script>", values: mergeProposal(P, left, right),
  });
  assert.ok(!html.includes("<img src=x"));
  assert.ok(!html.includes("<script>"));
  // A name breaking out of the textarea it was written into would leave a stray closing tag; the
  // count has to match the textareas the window opened itself.
  assert.equal((html.match(/<\/textarea>/g) || []).length, (html.match(/<textarea/g) || []).length);
  assert.ok(html.includes("&lt;/textarea&gt;"), "the name is escaped, not stripped");
});
