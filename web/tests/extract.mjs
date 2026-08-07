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

const html = readFileSync(INDEX_HTML, "utf8");

const source = [
  sliceStatement(html, "const esc = "),
  sliceFunction(html, "function mdInline("),
  sliceFunction(html, "function mdRenderInline("),
  sliceFunction(html, "function mdRender("),
  "return { esc, mdInline, mdRenderInline, mdRender };",
].join("\n");

export const { esc, mdInline, mdRenderInline, mdRender } = new Function(source)();
