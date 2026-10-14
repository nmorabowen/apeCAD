// The UI string table (ADR 0031 §2): register lint, placeholders, refusal grammar, and
// every t("id") the client calls exists. Run: node --test tests/js/*.test.mjs
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";

import { T, entities, refusalText, t } from "../../src/apeCAD/scratchpad/static/js/strings.js";

const JS_DIR = new URL("../../src/apeCAD/scratchpad/static/js/", import.meta.url);

// Dash pause, ellipsis, exclamation, question mark, verdict chips, the reader addressed.
const FORBIDDEN = /—|–|\.\.\.|…|!|\?|\bOK\b|\bokay\b|\byou\b|\byour\b|\bwe\b|\bplease\b|\boops\b/i;

test("no string breaks the notes-on-drawings register", () => {
  for (const [id, text] of Object.entries(T)) {
    assert.doesNotMatch(text, FORBIDDEN, `${id}: ${text}`);
    assert.equal(text, text.trim(), `${id} has stray whitespace`);
  }
});

test("hints and results are sentences that end in a full stop", () => {
  for (const [id, text] of Object.entries(T)) {
    if (!/^(tool|hint|done|grid|view)\./.test(id) || id === "grid.placeholder") continue;
    assert.match(text, /\.$/, `${id} does not end in a full stop: ${text}`);
  }
});

test("t fills placeholders and leaves unknown ones visible", () => {
  assert.equal(t("done.moved", { entities: entities(3) }), "Moved 3 entities.");
  assert.equal(t("done.delete", { entities: entities(1) }), "Deleted 1 entity.");
  assert.equal(t("hint.bezier.point", { n: 3 }), "Bézier: click control point 3.");
  assert.equal(t("hint.bezier.point"), "Bézier: click control point {n}.");
  assert.equal(t("no.such.id"), "no.such.id");
});

test("refusalText writes Refused: <reason>. with the reason capitalised", () => {
  assert.equal(refusalText("lines do not cross"), "Refused: Lines do not cross.");
  assert.equal(refusalText("nothing to undo."), "Refused: Nothing to undo.");
  assert.equal(
    refusalText("keep_id must be an endpoint of the trimmed line"),
    "Refused: keep_id must be an endpoint of the trimmed line.",
  );
  assert.equal(refusalText("Ø21 is not a designation"), "Refused: Ø21 is not a designation.");
  assert.equal(refusalText("Refused: Already wrapped."), "Refused: Already wrapped.");
  assert.equal(refusalText(t("reason.noCross")), "Refused: Those lines do not cross. Click another line.");
  assert.equal(refusalText(""), "Refused: unknown reason.");
});

test("every t() id the client uses is in the table", () => {
  const missing = [];
  for (const name of readdirSync(JS_DIR)) {
    if (!name.endsWith(".js")) continue;
    const source = readFileSync(new URL(name, JS_DIR), "utf8");
    for (const match of source.matchAll(/\bt\("([a-zA-Z.]+)"/g)) {
      if (!(match[1] in T)) missing.push(`${name}: ${match[1]}`);
    }
    for (const match of source.matchAll(/\bt\(`(tool|filter|filters)\.\$\{/g)) {
      const prefix = `${match[1]}.`;
      assert.ok(Object.keys(T).some((id) => id.startsWith(prefix)), `${name}: no ${prefix}* ids`);
    }
  }
  assert.deepEqual(missing, []);
  for (const filter of ["point", "line", "face", "solid", "element", "section"]) {
    assert.ok(`filter.${filter}` in T && `filters.${filter}` in T, filter);
  }
});
