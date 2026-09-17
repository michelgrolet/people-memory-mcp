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
