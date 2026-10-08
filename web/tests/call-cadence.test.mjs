import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

// The dashboard is one file with no build step, so the functions under test are cut out of it and
// evaluated as they ship. A renamed function throws here instead of silently testing nothing.
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
function slice(declaration) {
  const start = html.indexOf(declaration);
  if (start === -1) throw new Error(`web/index.html no longer declares: ${declaration}`);
  const open = html.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < html.length; i++) {
    if (html[i] === "{") depth++;
    else if (html[i] === "}" && --depth === 0) return html.slice(start, i + 1);
  }
  throw new Error(`unbalanced braces after: ${declaration}`);
}
const ctx = vm.createContext({});
vm.runInContext(
  [slice("function ago("), slice("function localIso("), slice("function callDueIn("), slice("function callDueLabel("),
   slice("function callHint(")].join("\n"),
  ctx,
);
const call = (fn, p) => vm.runInContext(`${fn}(${JSON.stringify(p)})`, ctx);
const iso = daysFromToday => vm.runInContext(`localIso(Date.now() + ${daysFromToday} * 86400000)`, ctx);

test("no cadence means no due date and no label", () => {
  assert.equal(call("callDueIn", { callEvery: null, callDueOn: null }), null);
  assert.equal(call("callDueLabel", { callEvery: null, callDueOn: null }), "");
});

test("a call due three days out reads as upcoming", () => {
  const p = { callEvery: 14, callDueOn: iso(3) };
  assert.equal(call("callDueIn", p), 3);
  assert.equal(call("callDueLabel", p), "call in 3d");
});

test("a call due today and one five days late", () => {
  assert.equal(call("callDueLabel", { callEvery: 14, callDueOn: iso(0) }), "call due today");
  assert.equal(call("callDueLabel", { callEvery: 14, callDueOn: iso(-5) }), "call overdue 5d");
});

test("the hint under the field says when you last really talked", () => {
  assert.equal(call("callHint", { callEvery: 30, callDueOn: iso(-2), lastCall: iso(-32), daysSinceCall: 32 }),
    "last call 1m · call overdue 2d");
  assert.equal(call("callHint", { callEvery: 30, callDueOn: iso(10), lastCall: null }),
    "no call recorded · call in 10d");
  assert.equal(call("callHint", { callEvery: null, lastCall: iso(-3), daysSinceCall: 3 }), "last call 3d");
});

// The calls window counts a call the way the database does, and shows the days between calls.
vm.runInContext([slice("function isLiveChannel("), slice("function callHistory(")].join("\n"), ctx);
const run = src => JSON.parse(vm.runInContext(`JSON.stringify(${src})`, ctx));

test("a call is what is_live_channel() counts as one", () => {
  for (const ch of ["call", "visio", "irl", "video", "in person", "Phone", "coffee"])
    assert.equal(run(`isLiveChannel(${JSON.stringify(ch)})`), true, ch);
  for (const ch of ["whatsapp", "email", "sms", "linkedin", "call booked", null, ""])
    assert.equal(run(`isLiveChannel(${JSON.stringify(ch)})`), false, String(ch));
});

test("call history keeps live channels, newest first, with the days since the call before", () => {
  const rows = run(`callHistory(${JSON.stringify([
    { id: 1, happened_on: "2026-01-05", channel: "call" },
    { id: 2, happened_on: "2026-03-10", channel: "visio" },
    { id: 3, happened_on: "2026-02-01", channel: "whatsapp" },
    { id: 4, happened_on: "2026-03-29", channel: "irl" },
  ])})`);
  assert.deepEqual(rows.map(r => [r.id, r.gap]), [[4, 19], [2, 64], [1, null]]);
});

test("a gap across a daylight-saving change is a whole number of days", () => {
  const rows = run(`callHistory(${JSON.stringify([
    { id: 1, happened_on: "2026-03-20", channel: "call" },
    { id: 2, happened_on: "2026-04-03", channel: "call" },
  ])})`);
  assert.equal(rows[0].gap, 14);
});

// After a write the window recomputes the due date itself, with the rule the `person` view uses.
vm.runInContext(slice("function callsRecompute("), ctx);
test("a call logged today moves the next due date to today plus the cadence", () => {
  const p = run(`(() => { const p = { callEvery: 14, createdOn: "2025-01-01", interactions: [
    { happened_on: localIso(new Date()), channel: "call" }, { happened_on: "2026-01-05", channel: "email" }] };
    callsRecompute(p); return p; })()`);
  assert.equal(p.daysSinceCall, 0);
  assert.equal(p.callDueOn, iso(14));
});
test("with no call left, the due date counts from the day the record was created", () => {
  const p = run(`(() => { const p = { callEvery: 30, createdOn: "2026-02-01", interactions: [
    { happened_on: "2026-03-01", channel: "whatsapp" }] }; callsRecompute(p); return p; })()`);
  assert.equal(p.lastCall, null);
  assert.equal(p.lastContact, "2026-03-01");
  assert.equal(p.callDueOn, "2026-03-03");
});
