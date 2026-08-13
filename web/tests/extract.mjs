import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const INDEX_HTML = join(dirname(fileURLToPath(import.meta.url)), "..", "index.html");

/**
 * The dashboard is one self-contained `index.html` on purpose (no build step, no bundler), so its
 * functions cannot be imported. Rather than reimplement them here — a test that passes while the
 * shipped code rots is worse than no test — pull the real source out of the file and evaluate it.
 *
 * `sliceFunction` walks braces from the declaration, so the functions can move or be reordered in
 * the file without breaking this. A missing function throws loudly instead of silently testing
 * nothing.
 */
function sliceFunction(source, declaration) {
  const start = source.indexOf(declaration);
  if (start === -1) throw new Error(`web/index.html no longer declares: ${declaration}`);
  const open = source.indexOf("{", start);
  if (open === -1) throw new Error(`no body found for: ${declaration}`);
  let depth = 0;
  for (let i = open; i < source.length; i++) {
    if (source[i] === "{") depth++;
    else if (source[i] === "}" && --depth === 0) return source.slice(start, i + 1);
  }
  throw new Error(`unbalanced braces after: ${declaration}`);
}

function sliceStatement(source, declaration) {
  const start = source.indexOf(declaration);
  if (start === -1) throw new Error(`web/index.html no longer declares: ${declaration}`);
  const end = source.indexOf("\n", start);
  return source.slice(start, end === -1 ? undefined : end);
}

/**
 * `sliceStatement` stops at the first newline, which is wrong for a declaration whose value spans
 * lines (an object literal, a chained call). This walks to the semicolon that closes it at nesting
 * depth zero instead, so the constant can be reformatted in the page without breaking the tests.
 */
function sliceDeclaration(source, declaration) {
  const start = source.indexOf(declaration);
  if (start === -1) throw new Error(`web/index.html no longer declares: ${declaration}`);
  let depth = 0;
  for (let i = start; i < source.length; i++) {
    const c = source[i];
    if (c === "{" || c === "(" || c === "[") depth++;
    else if (c === "}" || c === ")" || c === "]") depth--;
    else if (c === ";" && depth === 0) return source.slice(start, i + 1);
  }
  throw new Error(`no statement end found for: ${declaration}`);
}

const html = readFileSync(INDEX_HTML, "utf8");

const source = [
  sliceStatement(html, "const esc = "),
  sliceFunction(html, "function mdInline("),
  sliceFunction(html, "function mdRenderInline("),
  sliceFunction(html, "function mdRender("),
  "return { esc, mdInline, mdRenderInline, mdRender };",
].join("\n");

export const { esc, mdInline, mdRenderInline, mdRender } = new Function(source)();

// `DATA`/`byId` are exposed as setters (not plain exports) because the extracted functions close
// over the `let` declarations below — reassigning them from outside the Function body wouldn't be
// seen by that closure, only calling back in through `setData`/`setById` is.
const familySource = [
  sliceStatement(html, "const esc = "),
  sliceStatement(html, "const initials = "),
  sliceStatement(html, "const TIE_COLOR = "),
  sliceStatement(html, "const AGENT_COLOR = "),
  sliceStatement(html, "const tieColor = "),
  "let DATA = { edges: [] };",
  "let byId = new Map();",
  sliceFunction(html, "function parentsOf("),
  sliceFunction(html, "function childrenOf("),
  sliceFunction(html, "function famRel("),
  sliceFunction(html, "function siblingsOf("),
  sliceFunction(html, "function partnersOf("),
  sliceFunction(html, "function uniqById("),
  sliceFunction(html, "function buildFamilyTree("),
  sliceFunction(html, "function famNodeHtml("),
  sliceStatement(html, "const edgeKindLabel = "),
  `return {
    esc, buildFamilyTree, famNodeHtml, edgeKindLabel,
    setData: d => { DATA = d; }, setById: m => { byId = m; },
  };`,
].join("\n");

export const { buildFamilyTree, famNodeHtml, edgeKindLabel, setData, setById } = new Function(familySource)();

// The GEDCOM importer decides who is the same person as whom, so a regression here writes a
// duplicate into the live graph. Same rule as above: run the shipped source, never a copy of it.
const gedSource = [
  sliceDeclaration(html, "const GED_MONTH = "),
  sliceDeclaration(html, "const gnorm = "),
  sliceDeclaration(html, "const GED_UNKNOWN_SURNAME = "),
  sliceDeclaration(html, "const GED_REASON_BASE = "),
  sliceFunction(html, "function gedFixCase("),
  sliceFunction(html, "function gedDate("),
  sliceFunction(html, "function gedParse("),
  sliceFunction(html, "function gedDice("),
  sliceFunction(html, "function gedBirthAgrees("),
  sliceFunction(html, "function gedFileDuplicates("),
  sliceFunction(html, "function gedMatch("),
  sliceFunction(html, "function gedBuildWrites("),
  `return { gedFixCase, gedDate, gedParse, gedBirthAgrees, gedFileDuplicates, gedMatch, gedBuildWrites };`,
].join("\n");

export const { gedFixCase, gedDate, gedParse, gedBirthAgrees, gedFileDuplicates, gedMatch, gedBuildWrites } =
  new Function(gedSource)();
