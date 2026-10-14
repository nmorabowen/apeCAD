// Unit tests for the revision poll (attach mode, ADR 0028). Run: node --test tests/js
import assert from "node:assert/strict";
import { test } from "node:test";

import { pollOnce } from "../../src/apeCAD/scratchpad/static/js/live.js";

function harness({ revision, drawn, busy = false }) {
  const calls = [];
  const state = { scene: drawn, busy };
  const deps = {
    fetchJson: async (path) => {
      calls.push(path);
      return path === "/api/revision" ? { revision } : { revision, entities: [] };
    },
    current: () => state.scene,
    apply: async (scene) => {
      state.scene = scene;
    },
    busy: () => state.busy,
  };
  return { calls, state, deps };
}

test("an unchanged revision fetches no scene", async () => {
  const { calls, deps } = harness({ revision: 3, drawn: { revision: 3 } });
  assert.equal(await pollOnce(deps), false);
  assert.deepEqual(calls, ["/api/revision"]);
});

test("a new revision redraws from /api/scene", async () => {
  const { calls, state, deps } = harness({ revision: 4, drawn: { revision: 3 } });
  assert.equal(await pollOnce(deps), true);
  assert.deepEqual(calls, ["/api/revision", "/api/scene"]);
  assert.equal(state.scene.revision, 4);
});

test("a lower revision (a restarted scratchpad) also redraws", async () => {
  const { state, deps } = harness({ revision: 0, drawn: { revision: 9 } });
  assert.equal(await pollOnce(deps), true);
  assert.equal(state.scene.revision, 0);
});

test("mid-gesture it waits", async () => {
  const { calls, deps } = harness({ revision: 4, drawn: { revision: 3 }, busy: true });
  assert.equal(await pollOnce(deps), false);
  assert.deepEqual(calls, []);
});

test("a scene the client replaced meanwhile is not overwritten", async () => {
  const { state, deps } = harness({ revision: 4, drawn: { revision: 3 } });
  const fetchJson = deps.fetchJson;
  deps.fetchJson = async (path) => {
    const reply = await fetchJson(path);
    if (path === "/api/scene") state.scene = { revision: 5 }; // a local post answered first
    return reply;
  };
  assert.equal(await pollOnce(deps), false);
  assert.equal(state.scene.revision, 5);
});
