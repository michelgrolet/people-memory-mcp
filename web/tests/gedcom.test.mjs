import { test } from "node:test";
import assert from "node:assert/strict";

import { gedFixCase, gedDate, gedParse, gedBirthAgrees, gedFileDuplicates, gedMatch, gedBuildWrites }
  from "./extract.mjs";

// A genealogy export has no email and no phone, so the importer resolves identity on name and
// birth date alone. Every test here is about the same question: when is it allowed to decide by
// itself, and when must it stop and ask? Getting that wrong writes a duplicate person into a graph
// that has no undo.
//
// Every name, date and place below is invented. Fixtures never carry real people.

const FILE = `0 HEAD
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Alder /BRENNICK/
1 SEX M
1 BIRT
2 DATE 1901
1 FAMS @F1@
0 @I2@ INDI
1 NAME Maren /Vosk/
1 SEX F
1 BIRT
2 DATE 1903
1 FAMS @F1@
0 @I3@ INDI
1 NAME Ilsa /BRENNICK/
1 SEX F
1 BIRT
2 DATE 09 JAN 1930
2 PLAC Ashford
1 FAMC @F1@
0 @I4@ INDI
1 NAME Corwin /BRENNICK/
1 SEX M
1 BIRT
2 DATE ABT 1935
1 DEAT Y
1 OCCU Wheelwright
1 FAMC @F1@
0 @F1@ FAM
1 MARR
2 DATE 12 JUL 1926
2 PLAC Marlowe
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I4@
0 TRLR
`;

const parsed = gedParse(FILE);
const noOne = [];

test("reads an all-caps surname as a name, not a shout", () => {
  assert.equal(gedFixCase("BRENNICK"), "Brennick");
  assert.equal(gedFixCase("VOSK-PELL"), "Vosk-Pell");
  assert.equal(gedFixCase("Halloway"), "Halloway");     // already mixed case, left alone
  assert.equal(gedFixCase("de La Tour"), "de La Tour");
});

test("a surname the file does not know is no surname", () => {
  const { individuals } = gedParse("0 @I1@ INDI\n1 NAME Perrin /x/\n");
  assert.equal(individuals[0].name, "Perrin");
  assert.equal(individuals[0].surname, "");
});

test("keeps a partial date partial instead of inventing a day", () => {
  assert.deepEqual(gedDate("1901"), { iso: "1901", precision: "year", approx: false, display: "1901" });
  assert.equal(gedDate("MAR 1901").iso, "1901-03");
  assert.equal(gedDate("09 JAN 1930").iso, "1930-01-09");
  assert.equal(gedDate("ABT 1885").approx, true);
  assert.equal(gedDate("BET 1830 AND 1840").iso, "1830");
  assert.equal(gedDate("Y"), null);                      // "DEAT Y" is a flag, not a date
  assert.equal(gedDate("sometime later").iso, null);
});

test("parses individuals and families with their events", () => {
  assert.equal(parsed.individuals.length, 4);
  assert.equal(parsed.individuals[0].name, "Alder Brennick");
  assert.equal(parsed.individuals[2].birth.place, "Ashford");
  assert.equal(parsed.individuals[3].occupation, "Wheelwright");
  assert.equal(parsed.families[0].chil.length, 2);
  assert.equal(parsed.families[0].marr.iso, "1926-07-12");
});

test("a birth date agrees at the coarser of the two precisions", () => {
  assert.equal(gedBirthAgrees({ iso: "1903" }, "1903-08-27"), 1);
  assert.equal(gedBirthAgrees({ iso: "1903" }, "1904-08-27"), -1);
  assert.equal(gedBirthAgrees({ iso: "1885", approx: true }, "1887-01-01"), 0);
  assert.equal(gedBirthAgrees({ iso: "1903" }, null), 0);
  assert.equal(gedBirthAgrees(null, "1903-08-27"), 0);
});

test("links an unambiguous name, and creates when nobody is close", () => {
  const rows = gedMatch(parsed.individuals, parsed.families, [
    { id: 7, name: "Alder Brennick", birthdate: null, facts: [] },
  ]);
  const by = Object.fromEntries(rows.map(r => [r.ind.name, r]));
  assert.equal(by["Alder Brennick"].action, "link");
  assert.equal(by["Alder Brennick"].targetId, 7);
  assert.equal(by["Maren Vosk"].action, "create");
});

test("a maiden name against a married name is a question, never a silent second record", () => {
  const rows = gedMatch(parsed.individuals, parsed.families, [
    { id: 9, name: "Maren Brennick", birthdate: "1903-08-27", facts: [] },
  ]);
  const row = rows.find(r => r.ind.name === "Maren Vosk");
  assert.equal(row.action, "review");
  assert.equal(row.candidates[0].person.id, 9);
  assert.equal(row.candidates[0].reason, "married");
});

test("the same name on two records is a question, whichever side it comes from", () => {
  const twoInGraph = gedMatch(parsed.individuals, parsed.families, [
    { id: 1, name: "Alder Brennick", birthdate: null, facts: [] },
    { id: 2, name: "Alder Brennick", birthdate: null, facts: [] },
  ]);
  assert.equal(twoInGraph.find(r => r.ind.name === "Alder Brennick").action, "review");

  // Two people in the file wanting the same record: neither may take it unasked.
  const twice = gedParse(FILE + "0 @I9@ INDI\n1 NAME Alder /BRENNICK/\n");
  const rows = gedMatch(twice.individuals, twice.families, [
    { id: 1, name: "Alder Brennick", birthdate: null, facts: [] },
  ]);
  const both = rows.filter(r => r.ind.name === "Alder Brennick");
  assert.equal(both.length, 2);
  assert.ok(both.every(r => r.action === "review" && r.targetId === null));
});

test("a name that matches but a birth date that does not is a question, not a new person", () => {
  const rows = gedMatch(parsed.individuals, parsed.families, [
    { id: 4, name: "Ilsa Brennick", birthdate: "1930-01-11", facts: [] },
  ]);
  const row = rows.find(r => r.ind.name === "Ilsa Brennick");
  assert.equal(row.action, "review");
  assert.equal(row.why, "same name, different birth date");
});

test("a repeated name inside the file is only a duplicate when nothing separates the two", () => {
  // Father and son share a name: the descent line separates them.
  const dynasty = gedParse(`0 @I1@ INDI
1 NAME Tobin /Frayne/
1 FAMS @F1@
0 @I2@ INDI
1 NAME Tobin /Frayne/
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 CHIL @I2@
`);
  assert.equal(gedFileDuplicates(dynasty.individuals, dynasty.families).length, 0);

  // Same name, same birth year, one record as a child and one as a spouse: nothing separates them.
  const split = gedParse(`0 @I1@ INDI
1 NAME Ottilie /Sarn/
1 BIRT
2 DATE 07 APR 1921
1 FAMC @F1@
0 @I2@ INDI
1 NAME Ottilie /Sarn/
1 BIRT
2 DATE 1921
1 FAMS @F2@
0 @F1@ FAM
1 CHIL @I1@
0 @F2@ FAM
1 WIFE @I2@
`);
  assert.equal(gedFileDuplicates(split.individuals, split.families).length, 1);
  assert.ok(gedMatch(split.individuals, split.families, noOne).every(r => r.action === "review"));
});

test("the write plan carries the family, the dates and nothing twice", () => {
  const rows = gedMatch(parsed.individuals, parsed.families, noOne);
  const plan = gedBuildWrites(rows, parsed.families, noOne);

  assert.equal(plan.creates.length, 4);
  // A full date belongs in the typed column; a partial one can only live as a fact.
  const ilsa = plan.creates.find(c => c.values.full_name === "Ilsa Brennick");
  assert.equal(ilsa.values.birthdate, "1930-01-09");
  assert.ok(!plan.facts.some(f => f.row.ind.name === "Ilsa Brennick" && f.key === "born"));
  const alder = plan.creates.find(c => c.values.full_name === "Alder Brennick");
  assert.equal(alder.values.birthdate, null);
  assert.ok(plan.facts.some(f => f.row.ind.name === "Alder Brennick" && f.key === "born" && f.date === "1901"));

  const kinds = plan.edges.reduce((a, e) => (a[e.kind] = (a[e.kind] || 0) + 1, a), {});
  assert.deepEqual(kinds, { partner: 1, parent: 4, sibling: 1 });
  const partner = plan.edges.find(e => e.kind === "partner");
  assert.equal(partner.since, "1926-07-12");
  assert.equal(partner.note, "married in Marlowe");
  // Directed: the parent is always on the a side.
  assert.ok(plan.edges.filter(e => e.kind === "parent")
    .every(e => ["Alder Brennick", "Maren Vosk"].includes(e.a.ind.name)));
  // "DEAT Y" is a death with no date, and it still gets recorded.
  assert.ok(plan.facts.some(f => f.row.ind.name === "Corwin Brennick" && f.key === "died" && f.value === "yes"));
  assert.ok(plan.facts.some(f => f.key === "occupation" && f.value === "Wheelwright"));
  assert.ok(plan.facts.some(f => f.key === "birth_place" && f.value === "Ashford"));
});

test("a skipped person takes no record, and their family links go with them", () => {
  const rows = gedMatch(parsed.individuals, parsed.families, noOne);
  rows.find(r => r.ind.name === "Maren Vosk").action = "skip";
  const plan = gedBuildWrites(rows, parsed.families, noOne);
  assert.equal(plan.creates.length, 3);
  assert.equal(plan.edges.filter(e => e.kind === "partner").length, 0);
  assert.equal(plan.edges.filter(e => e.kind === "parent").length, 2);
});

test("merging two records in the file writes one person carrying both halves", () => {
  const split = gedParse(`0 @I1@ INDI
1 NAME Ottilie /Sarn/
1 BIRT
2 DATE 07 APR 1921
1 FAMC @F1@
0 @I2@ INDI
1 NAME Ottilie /Sarn/
1 DEAT
2 DATE 2014
1 FAMS @F2@
0 @I3@ INDI
1 NAME Rennick /Sarn/
1 FAMS @F1@
0 @I4@ INDI
1 NAME Edmund /Pell/
1 FAMS @F2@
0 @F1@ FAM
1 HUSB @I3@
1 CHIL @I1@
0 @F2@ FAM
1 HUSB @I4@
1 WIFE @I2@
`);
  const rows = gedMatch(split.individuals, split.families, noOne);
  const first = rows.find(r => r.xref === "@I1@"), second = rows.find(r => r.xref === "@I2@");
  first.action = "create"; first.mergeInto = null;
  second.action = "merge"; second.mergeInto = "@I1@";
  const plan = gedBuildWrites(rows, split.families, noOne);

  assert.equal(plan.creates.length, 3);                     // Ottilie once, not twice
  assert.equal(plan.creates.filter(c => c.values.full_name === "Ottilie Sarn").length, 1);
  // Both halves of her life land on the surviving record.
  assert.ok(plan.facts.some(f => f.key === "died" && f.value === "2014"));
  // Her father and her husband both point at the same person, which is the whole point of merging.
  // The partner pair is ordered by xref, matching what the database's own canonicalization does.
  assert.deepEqual(
    plan.edges.map(e => `${e.a.ind.name} ${e.kind} ${e.b.ind.name}`).sort(),
    ["Ottilie Sarn partner Edmund Pell", "Rennick Sarn parent Ottilie Sarn"],
  );
});

test("a fact already on the record is not written a second time", () => {
  const graph = [{ id: 3, name: "Alder Brennick", birthdate: null,
                   facts: [{ key: "born", value: "1901", date: "1901" }] }];
  const rows = gedMatch(parsed.individuals, parsed.families, graph);
  const plan = gedBuildWrites(rows, parsed.families, graph);
  assert.equal(rows.find(r => r.ind.name === "Alder Brennick").action, "link");
  assert.ok(!plan.facts.some(f => f.row.targetId === 3 && f.key === "born"));
});

test("re-importing the same file a second time creates nobody", () => {
  const rows = gedMatch(parsed.individuals, parsed.families, noOne);
  const first = gedBuildWrites(rows, parsed.families, noOne);

  // Replay what the first import wrote back into the graph, then run the whole thing again.
  const graph = first.creates.map((c, i) => ({
    id: 100 + i, name: c.values.full_name, birthdate: c.values.birthdate,
    facts: first.facts.filter(f => f.row === c.row).map(f => ({ key: f.key, value: f.value, date: f.date })),
  }));
  const idOf = new Map(first.creates.map((c, i) => [c.row.xref, 100 + i]));
  const edges = first.edges.map(e => ({ a: idOf.get(e.a.xref), b: idOf.get(e.b.xref), kind: e.kind }));
  const again = gedMatch(parsed.individuals, parsed.families, graph);
  const second = gedBuildWrites(again, parsed.families, graph, edges);

  assert.equal(second.creates.length, 0);
  assert.equal(second.facts.length, 0);
  assert.equal(second.edges.length, 0);
  assert.ok(again.every(r => r.action === "link"));
});

test("a link already in the graph is left alone, whichever way round it is stored", () => {
  const rows = gedMatch(parsed.individuals, parsed.families, [
    { id: 1, name: "Alder Brennick", birthdate: null, facts: [] },
    { id: 2, name: "Maren Vosk", birthdate: null, facts: [] },
    { id: 3, name: "Ilsa Brennick", birthdate: "1930-01-09", facts: [] },
  ]);
  // Stored b-then-a: a symmetric link reads both ways, so it must not be written a second time.
  const plan = gedBuildWrites(rows, parsed.families, [], [{ a: 2, b: 1, kind: "partner" },
                                                          { a: 1, b: 3, kind: "parent" }]);
  assert.equal(plan.edges.filter(e => e.kind === "partner").length, 0);
  assert.equal(plan.edges.filter(e => e.kind === "parent").length, 3);   // one of four already there
});
