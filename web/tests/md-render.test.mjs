import { test } from "node:test";
import assert from "node:assert/strict";

import { esc, mdRender, mdRenderInline } from "./extract.mjs";

// The renderer is homemade regex over already-escaped text, which is safe only as long as `esc`
// keeps escaping quotes: without that, a link target could close the href and open an attribute.
// These tests exist to make that dependency fail loudly if either half is ever changed alone.

test("esc neutralizes every character the renderer relies on", () => {
  assert.equal(esc(`<&>"'`), "&lt;&amp;&gt;&quot;&#39;");
});

test("renders the formatting the editor advertises", () => {
  assert.equal(mdRender("# Title"), "<h1>Title</h1>");
  assert.equal(mdRender("### Deep"), "<h3>Deep</h3>");
  assert.equal(mdRender("**bold**"), "<p><strong>bold</strong></p>");
  assert.equal(mdRender("*italic*"), "<p><em>italic</em></p>");
  assert.equal(mdRender("_italic_"), "<p><em>italic</em></p>");
  assert.equal(mdRender("`code()`"), "<p><code>code()</code></p>");
  assert.equal(mdRender("- one\n- two"), "<ul><li>one</li><li>two</li></ul>");
  assert.equal(mdRender("1. one\n2. two"), "<ol><li>one</li><li>two</li></ol>");
});

test("joins wrapped lines into one paragraph and splits on a blank line", () => {
  assert.equal(mdRender("one\ntwo"), "<p>one two</p>");
  assert.equal(mdRender("one\n\ntwo"), "<p>one</p><p>two</p>");
});

test("empty input renders nothing rather than an empty tag", () => {
  assert.equal(mdRender(""), "");
  assert.equal(mdRender("   \n  "), "");
  assert.equal(mdRender(null), "");
  assert.equal(mdRenderInline(undefined), "");
});

test("inline rendering keeps a fact value on one line", () => {
  assert.equal(mdRenderInline("a\nb"), "a b");
});

test("links render only for http(s) and carry noopener", () => {
  assert.equal(
    mdRender("[site](https://example.com/x)"),
    '<p><a href="https://example.com/x" target="_blank" rel="noopener">site</a></p>',
  );
  // A non-http scheme is left as plain text inside the paragraph, which is the safe outcome:
  // what must never happen is it becoming a clickable href.
  const dangerous = mdRender("[click](javascript:alert(1))");
  assert.ok(!dangerous.includes("<a "), dangerous);
  assert.ok(!dangerous.includes("href="), dangerous);
});

test("raw HTML in a note is shown, never executed", () => {
  const out = mdRender("<script>alert(1)</script>");
  assert.ok(!out.includes("<script"), out);
  assert.ok(out.includes("&lt;script&gt;"), out);
});

test("a link target cannot break out of the href attribute", () => {
  // Needs no space and no parenthesis to survive the regex, so it is the realistic attempt.
  const out = mdRender('[x](https://a"onmouseover=location=name)');
  assert.ok(!out.includes('"onmouseover'), out);
  assert.ok(out.includes("&quot;onmouseover"), out);
});

test("an event handler hidden in link text stays text", () => {
  const out = mdRender('[<img src=x onerror=alert(1)>](https://example.com)');
  assert.ok(!out.includes("<img"), out);
  assert.ok(out.includes("&lt;img"), out);
});

test("entities cannot be smuggled through, because & is escaped first", () => {
  assert.ok(mdRender("&lt;script&gt;").includes("&amp;lt;"), "a literal &lt; must stay literal");
});

test("header level never escapes h1-h3", () => {
  assert.equal(mdRender("#### four"), "<p>#### four</p>");
});
