import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// The dashboard runs one third-party module inside the authenticated session, so the version it
// loads is a security decision, not a packaging detail. `@supabase/supabase-js@2` floats: the CDN
// serves whatever the newest 2.x is at the moment the page opens, which means an upstream publish
// changes what runs here with nobody deciding anything. Pinned imports only.
const HTML = readFileSync(fileURLToPath(new URL("../index.html", import.meta.url)), "utf8");

// `https://host/@scope/name@version` and `https://host/name@version`, as written in an import.
const REMOTE_IMPORT = /\bfrom\s+"(https?:\/\/[^"]+)"/g;

test("every remote module the dashboard imports is pinned to an exact version", () => {
  const imports = [...HTML.matchAll(REMOTE_IMPORT)].map((m) => m[1]);
  assert.ok(imports.length > 0, "expected the dashboard to import at least one remote module");
  for (const url of imports) {
    const version = url.split("@").pop();
    assert.match(
      version,
      /^\d+\.\d+\.\d+$/,
      `${url} is not pinned: a bare major or minor lets the CDN choose what runs in the session`,
    );
  }
});

test("no remote script or module arrives through a tag that skips the import check", () => {
  // A `<script src="https://…">` would load third-party code without going through the rule above.
  const tags = [...HTML.matchAll(/<script\b[^>]*\bsrc\s*=\s*"([^"]+)"/g)].map((m) => m[1]);
  const remote = tags.filter((src) => /^https?:\/\//.test(src));
  assert.deepEqual(remote, [], `remote <script src> found: ${remote.join(", ")}`);
});
