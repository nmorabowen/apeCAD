"""The 2-D client draws v2 (C5 record §3 "Client data" A and "Client drawing"; C5-S3).

The oracles come from outside the client: `render`'s drawables (C5-S1) on the 11 committed
v2 fixtures, the v2 draft's items (one projector), the v1 and v2 lints, and
`require_v1_expressible`. Each JS check runs the shipped modules under node, driven from here.
Record §4 invariants 1, 7 and 8, the scene's warnings, and a too-deep body over the live
transport. The pure painting oracles (3, 4, 12, 10^5 bars) are `tests/js/section-v2.test.mjs`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Thread
from typing import Any, cast

import pytest

from _section_fixtures import BUILDERS
from _section_fixtures_v2 import BUILDERS_V2, fixture_path_v2
from apeCAD import catalog
from apeCAD.document import Document
from apeCAD.errors import DocumentError
from apeCAD.geometry import XYZ
from apeCAD.ops import PointAt
from apeCAD.render.drawable import SECTION_LAYERS
from apeCAD.render.scene import drawables, entity_map
from apeCAD.scratchpad.payload import scene_payload
from apeCAD.scratchpad.section_assets import SECTION_DIR
from apeCAD.scratchpad.server import ScratchpadServer
from apeCAD.section.draft_v2 import require_v1_expressible
from apeCAD.section.lint import lint_section_v2
from apeCAD.section_draft import section_draft

Json = dict[str, Any]
FIXTURES = sorted(BUILDERS_V2)
NOT_SECTION_KEYS = {  # scene keys the 2-D client does not draw: sketch kinds and metadata
    "document", "points", "lines", "polylines", "boxes", "faces", "solids", "circles", "arcs",
    "ellipses", "beziers", "warnings", "tags", "brep",
}  # fmt: skip


def _node() -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    return node


def _module(name: str) -> str:
    return SECTION_DIR.joinpath(name).as_uri()


def _run(script: str, timeout: float = 60) -> str:
    res = subprocess.run(
        [_node(), "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    return res.stdout


def _client_display(scenes: dict[str, Json], tmp_path: Path) -> dict[str, Json]:
    """Per scene, the client's display list as `[[id, layer], ...]`, its not-drawn messages
    and `v1Unsayable`, from the shipped `display2d.js` and `transport.js`."""
    data = tmp_path / "scenes.json"
    data.write_text(json.dumps(scenes), encoding="utf-8")
    script = f"""
    import fs from "node:fs";
    import {{ SECTION_KINDS, displayList }} from {_module("display2d.js")!r};
    import {{ normalizeScene, v1Unsayable }} from {_module("transport.js")!r};
    const scenes = JSON.parse(fs.readFileSync({str(data)!r}, "utf8"));
    const out = {{ kinds: Object.keys(SECTION_KINDS), scenes: {{}} }};
    for (const [name, raw] of Object.entries(scenes)) {{
      const scene = normalizeScene(raw);
      const {{ entries, notDrawn }} = displayList(scene);
      out.scenes[name] = {{ entries: entries.map((e) => [e.id, e.layer]),
        notDrawn: notDrawn.map((n) => n.message), unsayable: v1Unsayable(scene) }};
    }}
    process.stdout.write(JSON.stringify(out));
    """
    return cast(Json, json.loads(_run(script)))


def _render_layers(document: Document) -> list[list[object]]:
    """`render`'s section drawables as `[[id, layer], ...]`, in the order it paints them."""
    entities = entity_map(document)
    found = drawables(entities, set(entities), None)
    return [[d.entity_id, d.layer] for layer in SECTION_LAYERS for d in found if d.layer == layer]


def _v1_says(document: Document) -> bool:
    try:
        require_v1_expressible(entity_map(document), "the scene")
    except DocumentError:
        return False
    return True


# ---- invariant 1: the client draws what render draws, on the same layer -----------------


def test_the_client_draws_every_fixture_id_on_renders_layer(tmp_path: Path) -> None:
    scenes = {name: scene_payload(BUILDERS_V2[name]()) for name in FIXTURES}
    client = _client_display(scenes, tmp_path)
    for name in FIXTURES:
        document = BUILDERS_V2[name]()
        got = client["scenes"][name]
        assert got["notDrawn"] == [], (name, got["notDrawn"])
        assert got["entries"] == _render_layers(document), name
        # Every id the committed fixture lists, `templates[]` excepted (C1-S5's oracle source).
        section = cast(Json, json.loads(fixture_path_v2(name).read_text(encoding="utf-8")))
        listed = {
            cast(int, item["id"])
            for key, items in cast(Json, section["section"]).items()
            if key not in ("templates", "materials_used")
            for item in cast(list[Json], items)
        }
        drawn = {cast(int, entry[0]) for entry in got["entries"]}
        assert listed and listed <= drawn, (name, sorted(listed - drawn))


def test_the_client_lists_every_section_key_of_the_scene(tmp_path: Path) -> None:
    """A section list added to `scene_payload` fails here until `display2d.js` knows it."""
    scene = scene_payload(BUILDERS_V2["cft_rect_template"]())
    client = _client_display({"one": scene}, tmp_path)
    assert set(client["kinds"]) == set(scene) - NOT_SECTION_KEYS


# ---- invariant 7: one projector ----------------------------------------------------------


def _less(item: Json, *keys: str) -> Json:
    return {k: v for k, v in item.items() if k not in keys}


@pytest.mark.parametrize("name", FIXTURES)
def test_scene_v2_items_equal_the_v2_drafts(name: str) -> None:
    document = BUILDERS_V2[name]()
    scene = scene_payload(document)
    block = cast(Json, section_draft(document, version=2, commit=None)["section"])
    draft_faces = {cast(int, f["id"]): f for f in cast(list[Json], block["faces"])}
    v1_ids = {cast(int, f["entity_id"]) for f in cast(list[Json], scene["concrete_faces"])}
    scene_faces = cast(list[Json], scene["section_faces"])
    assert {cast(int, f["entity_id"]) for f in scene_faces} | v1_ids == set(draft_faces)
    for item in scene_faces:
        expected = _less(draft_faces[cast(int, item["entity_id"])], "id", "template_id")
        assert _less(item, "entity_id") == expected
    ties = cast(list[Json], scene["circular_ties"])
    draft_ties = cast(list[Json], block["circular_ties"])
    assert [_less(t, "entity_id") for t in ties] == [
        _less(t, "id", "template_id") for t in draft_ties
    ]
    templates = cast(list[Json], scene["templates"])
    assert [_less(t, "entity_id", "child_ids", "label") for t in templates] == [
        _less(t, "id") for t in cast(list[Json], block["templates"])
    ]
    for template in templates:  # a child's `template_id` is its template's `child_ids`
        owned = {
            cast(int, item["id"])
            for key in ("faces", "bars", "hoops", "crossties", "circular_ties", "cover_guides")
            for item in cast(list[Json], block[key])
            if item.get("template_id") == template["entity_id"]
        }
        assert owned and owned <= set(cast(list[int], template["child_ids"])), name


# ---- the scene's warnings ----------------------------------------------------------------


@pytest.mark.parametrize("name", FIXTURES)
def test_scene_warnings_are_v2s_only_when_v1_cannot_say_the_document(name: str) -> None:
    document = BUILDERS_V2[name]()
    warnings = scene_payload(document)["warnings"]
    if _v1_says(document):
        assert warnings == [w.to_dict() for w in document.section_lint()], name
    else:
        assert warnings == [w.to_dict() for w in lint_section_v2(entity_map(document))], name


def test_rect_column_ties_warns_nothing_in_the_scene() -> None:
    """The record's probe: v1's lint gave 11 warnings on `rect_column_ties`, v2's none."""
    document = BUILDERS_V2["rect_column_ties"]()
    assert len(document.section_lint()) == 11
    assert scene_payload(document)["warnings"] == []


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_a_v1_scene_keeps_v1s_lint_and_empty_v2_lists(name: str) -> None:
    document = BUILDERS[name]()
    scene = scene_payload(document)
    assert scene["warnings"] == [w.to_dict() for w in document.section_lint()]
    assert (scene["section_faces"], scene["circular_ties"], scene["templates"]) == ([], [], [])


# ---- invariant 8: no client path writes a v1 draft that drops a v2 entity ----------------


def _steel_bar_document() -> Document:
    """A v1 outline with one bar naming its steel: v1 cannot say it (ADR 0039 D6)."""
    document = Document()
    ring = [(0, 0), (400, 0), (400, 400), (0, 400)]
    document.add_section_outline([PointAt(XYZ(x, y, 0.0)) for x, y in ring], "C30")
    document.add_bar(100.0, 100.0, "Ø16", material="B500")
    return document


def test_the_client_knows_what_v1_cannot_say(tmp_path: Path) -> None:
    documents = {name: BUILDERS_V2[name]() for name in FIXTURES}
    documents |= {f"v1_{name}": BUILDERS[name]() for name in BUILDERS}
    documents["steel_bar"] = _steel_bar_document()
    client = _client_display({k: scene_payload(d) for k, d in documents.items()}, tmp_path)
    says = {name: _v1_says(d) for name, d in documents.items()}
    assert says["steel_bar"] is False and says["v1_rect_boundary_hoops"] is True
    assert not all(says.values()) and any(says.values())
    for name in documents:
        unsayable = client["scenes"][name]["unsayable"]
        assert (unsayable is None) is says[name], (name, unsayable)


@pytest.fixture
def server() -> Iterator[ScratchpadServer]:
    bound = ScratchpadServer(("127.0.0.1", 0), Document())
    thread = Thread(target=bound.serve_forever, daemon=True)
    thread.start()
    yield bound
    bound.shutdown()
    bound.server_close()


def test_http_transport_never_writes_a_lossy_v1_draft(
    server: ScratchpadServer, tmp_path: Path
) -> None:
    """Load each fixture through the live Python transport: the client's draft is v1 only when
    v1 can say the document, and `null` otherwise, also after an edit (no onChange with one)."""
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/api/section/transport"
    drafts = {name: section_draft(BUILDERS_V2[name](), version=2) for name in FIXTURES}
    says = {name: _v1_says(BUILDERS_V2[name]()) for name in FIXTURES}
    data = tmp_path / "drafts.json"
    data.write_text(json.dumps({"drafts": drafts, "says": says}), encoding="utf-8")
    script = f"""
    import assert from "node:assert/strict";
    import fs from "node:fs";
    import {{ create, httpTransport }} from {_module("apecad-section.js")!r};
    const {{ drafts, says }} = JSON.parse(fs.readFileSync({str(data)!r}, "utf8"));
    for (const [name, draft] of Object.entries(drafts)) {{
      const changes = [];
      const onChange = (d) => changes.push(d);
      const ed = create({{}}, {{ transport: httpTransport({url!r}), onChange }});
      await new Promise((r) => setTimeout(r, 20));
      const res = await ed.loadDraft(draft);
      assert.equal(res.ok, true, name);
      const nV2 = ed.getScene().section_faces.length + ed.getScene().circular_ties.length;
      if (says[name]) {{
        assert.equal(nV2, 0, name);
        assert.equal(ed.getDraft().version, 1, name);
      }} else {{
        assert.equal(ed.getDraft(), null, name);
        assert.equal(res.draft, null, name);
        const edit = await ed.applyOp({{ op: "AddBar", x_mm: 1, y_mm: 1, designation: "Ø16" }});
        assert.equal(edit.ok, true, name);
        assert.equal(ed.getDraft(), null, name);
        assert.deepEqual(changes, [], name);
      }}
      ed.dispose();
    }}
    """
    _run(script, timeout=120)


# ---- huge input over the live transport --------------------------------------------------


def test_a_too_deep_body_is_refused_and_the_client_keeps_working(
    server: ScratchpadServer,
) -> None:
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/api/section/transport"
    script = f"""
    import assert from "node:assert/strict";
    import {{ create, httpTransport }} from {_module("apecad-section.js")!r};
    const ed = create({{}}, {{ transport: httpTransport({url!r}) }});
    await new Promise((r) => setTimeout(r, 20));
    const nested = (depth) => {{ let v = []; for (let i = 0; i < depth; i++) v = [v]; return v; }};
    // 1500 levels: node sends it and the server refuses it by name (too deep to parse, or, where
    // the Python parses that deep, not an op); 10^5: the client cannot even write it as JSON,
    // and refuses it by name instead of throwing.
    const server = /body is nested too deeply to parse|each op must be an object/;
    const client = /the request is nested too deeply to send as JSON/;
    for (const [depth, why] of [[1500, server], [100000, client]]) {{
      const ops = nested(depth);
      const res = await ed.loadDraft({{ schema: "apeCAD.document.v1", units: "mm", ops }});
      assert.equal(res.ok, false, String(depth));
      assert.equal(res.status, 422, String(depth));
      assert.match(res.error.message, why);
    }}
    const after = await ed.applyOp({{ op: "AddBar", x_mm: 1, y_mm: 1, designation: "Ø16" }});
    assert.equal(after.ok, true, "the next request is served");
    assert.equal(ed.getScene().bars.length, 1);
    ed.dispose();
    """
    _run(script)


# ---- C5-S4: the client edits v2, over the live Python transport --------------------------
#
# A scripted session drives the shipped client as a user would: tools from `setTool`, points
# typed in the command line, keys on the container, the toolbar's buttons. The transport is
# wrapped to log each request (and the HTTP body it became) and each response's `ok`.

_HARNESS = """
import {{ create, httpTransport }} from {entry!r};
const requests = [], bodies = [];
const realFetch = globalThis.fetch;
globalThis.fetch = (u, init) => {{ bodies.push(init.body); return realFetch(u, init); }};
const inner = httpTransport({url!r});
let inflight = 0, lastError = null;
const transport = async (req) => {{
  inflight += 1;
  try {{
    const res = await inner(req);
    requests.push({{ req: JSON.stringify(req), ok: Boolean(res && res.ok) }});
    if (res && !res.ok) lastError = res.error;
    return res;
  }} finally {{ inflight -= 1; }}
}};
const listeners = {{}};
const container = {{ children: [], appendChild(c) {{ this.children.push(c); return c; }},
  addEventListener(t, f) {{ listeners[t] = f; }}, removeEventListener() {{}} }};
const settle = async () => {{
  do {{ await new Promise((r) => setTimeout(r, 2)); }} while (inflight > 0);
}};
const changes = [];
const ed = create(container, {{ transport, onChange: (d) => changes.push(d), {options} }});
await settle();
const [toolbar, stage, bottom] = container.children[0].children;
const [prompt, cmd] = bottom.children;
const props = () => stage.children[1].children[0].children.map((c) => c.textContent);
const tools = toolbar.children.map((b) => b.dataset.tool).filter(Boolean);
const type = async (...inputs) => {{
  for (const text of inputs) {{
    cmd.value = text;
    cmd.dispatchEvent({{ type: "keydown", key: "Enter" }});
    await settle();
  }}
}};
const key = async (evt) => {{
  listeners.keydown({{ target: null, preventDefault() {{}}, ...evt }});
  await settle();
}};
const button = async (action) => {{
  toolbar.children.find((b) => b.dataset.action === action).dispatchEvent({{ type: "click" }});
  await settle();
}};
"""

V1_TOOLS = [
    "select", "rect", "polygon", "opening", "wall-chain", "wall-leg", "cover", "bar", "bar-row",
    "bars-edge", "hoop", "crosstie", "delete",
]  # fmt: skip
V2_TOOLS = [
    "select", "rect", "polygon", "circle", "hole", "wall-chain", "wall-leg", "cover", "bar",
    "bar-row", "hoop", "crosstie", "delete",
]  # fmt: skip

# sha-256 of the v1 session's log below, run against the client at apeCAD b4b6e63 (before
# C5-S4) in a scratch tree: the requests byte for byte, and each HTTP body less the echoed
# `document` and `redo` (state the server wrote, which the client only passes back).
V1_LOG_SHA256 = "203c04ef36764ad169ebcc1a1169bbe7ec0b5011785738528f6341b72f07069a"


def _session(server: ScratchpadServer, body: str, options: str = "") -> Json:
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/api/section/transport"
    head = _HARNESS.format(entry=_module("apecad-section.js"), url=url, options=options)
    return cast(Json, json.loads(_run(head + body, timeout=120)))


def test_v1_mode_sends_the_requests_it_sent_before_c5_s4(server: ScratchpadServer) -> None:
    """Record §4 invariant 9 (v1 half) and the 13 v1 tool ids: a scripted v1 session posts
    exactly what the b4b6e63 client posted, and never a `draft`."""
    out = _session(
        server,
        """
    ed.setTool("rect"); await type("0,0", "400,600");
    ed.setTool("opening"); await type("100,100", "200,100", "200,200", "c");
    ed.setTool("polygon"); await type("500,0", "@300,0", "@0,300", "c");
    ed.setTool("cover"); await type("10,10");
    ed.setTool("bar"); await type("60,60", "340,60");
    ed.setTool("bar-row"); await type("60,540", "340,540");
    ed.setTool("bars-edge"); await type("0,0");
    ed.setTool("wall-chain"); await type("1000,0", "2000,0", "c");
    ed.setTool("wall-leg"); await type("1000,500", "2000,500");
    ed.setTool("select"); await type("60,60");
    await key({ key: "Delete" }); await key({ key: "z", ctrlKey: true });
    await key({ key: "y", ctrlKey: true });
    await ed.undo(); await ed.redo(); await settle();
    await ed.applyOp({ op: "Delete", entity_ids: [ed.getScene().bars[0].id] });
    await ed.loadDraft({ schema: "apeCAD.section-seed", version: 1, units: "mm", section: {
      concrete_faces: [{ ring_mm: [[0, 0], [300, 0], [300, 300], [0, 300]], material: "C30" }],
      bars: [] } });
    await ed.applyOp({ op: "AddBar", x_mm: 50, y_mm: 50, designation: "Ø16" });
    const strip = (b) => {
      const o = JSON.parse(b); delete o.document; delete o.redo; return JSON.stringify(o);
    };
    process.stdout.write(JSON.stringify({ tools, requests: requests.map((r) => r.req),
      bodies: bodies.map(strip), version: ed.getDraft()?.version ?? null }));
    """,
    )
    assert out["tools"] == V1_TOOLS
    actions = [json.loads(r)["action"] for r in out["requests"]]
    assert "draft" not in actions and len(actions) >= 18, actions
    log = json.dumps({"requests": out["requests"], "bodies": out["bodies"]}, ensure_ascii=False)
    digest = hashlib.sha256(log.encode("utf-8")).hexdigest()
    assert digest == V1_LOG_SHA256, (digest, actions)
    assert out["version"] == 1


_COLUMN = {  # catalog/template_entries.py's example, moved clear of the freehand faces
    "material": "C30", "b": 400, "h": 600, "center_mm": [1500, 300], "cover": 40, "nx": 3,
    "ny": 3, "bar": "Ø20", "tie": "Ø10", "tie_spacing": 150, "crossties": "all",
}  # fmt: skip


def _xyz(x: float, y: float) -> Json:
    return {"xyz": [x, y, 0]}


def _ids(draft: Json) -> set[int]:
    section = cast(Json, draft["section"])
    return {
        cast(int, item["id"])
        for key, items in section.items()
        if key not in ("templates", "materials_used")
        for item in cast(list[Json], items)
    }


def test_v2_mode_edits_through_the_live_transport(server: ScratchpadServer) -> None:
    """Record §4 invariants 9-11 and the S4 oracle. Each v2 tool posts the op the test names
    here, and `getDraft()` (and `onChange`) deep-equals `section_draft(doc, version=2)` of a
    document the test builds itself from those ops, after every apply, undo and redo. A locked
    child refuses with the server's `TEMPLATE_LOCKED`, shown as `Refused: <message>`; Delete
    on a child takes its whole template; Explode keeps the child ids."""
    out = _session(
        server,
        f"""
    const steps = [];
    const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
    const snap = (label) => {{
      steps.push({{ label, draft: ed.getDraft(), prompt: prompt.textContent, props: props(),
        changes: changes.length, error: lastError?.code ?? null,
        changeIsDraft: changes.length ? same(changes.at(-1), ed.getDraft()) : null }});
      lastError = null;
    }};
    snap("open");
    ed.setParam("material", "C30"); ed.setTool("rect"); await type("0,0", "400,600"); snap("rect");
    ed.setParam("role", "steel"); ed.setParam("material", "S355");
    ed.setTool("circle"); await type("600,300", "@50,0"); snap("circle");
    ed.setParam("role", "void"); ed.setTool("polygon");
    await type("100,400", "300,400", "200,500", "c"); snap("polygon");
    ed.setParam("role", "concrete"); ed.setParam("material", "C30");
    ed.setTool("hole"); await type("100,100", "@100,0", "@0,100", "c"); snap("hole");
    ed.setTool("cover"); await type("350,50"); snap("cover");
    ed.setTool("bar"); await type("60,60"); snap("bar");
    await ed.undo(); snap("undo");
    await ed.redo(); snap("redo");
    ed.setTool("delete"); await type("60,60"); snap("delete");
    const column = {json.dumps(_COLUMN)};
    const add = {{ op: "AddSectionTemplate", template: "rect_column", template_params: column }};
    await ed.applyOp(add);
    snap("template");
    const tpl = ed.getScene().templates[0];
    const child = ed.getScene().bars.find((b) => tpl.child_ids.includes(b.id));
    const at = `${{child.x_mm}},${{child.y_mm}}`;
    ed.setTool("hole"); await type("1450,250", "@100,0", "@0,100", "c"); snap("hole-on-child");
    await ed.applyOp({{ op: "Delete", entity_ids: [child.id] }}); snap("delete-child");
    ed.setTool("select"); await type(at); snap("select");
    await key({{ key: "Delete" }}); snap("delete-template");
    await ed.undo(); snap("undo-delete");
    ed.setTool("select"); await type(at); await button("explode"); snap("explode");
    process.stdout.write(JSON.stringify({{ tools, steps, requests, template: tpl.id }}));
    """,
        options="version: 2",
    )
    assert out["tools"] == V2_TOOLS
    template_id = cast(int, out["template"])
    document = Document()
    created: dict[str, int] = {}

    def apply(label: str, op: Json) -> None:
        name, params = catalog.split_request(op)
        created_id = catalog.apply(document, name, params).created_id
        if isinstance(created_id, int):
            created[label] = created_id

    expected: dict[str, Callable[[], object]] = {
        "rect": lambda: apply("rect", {
            "op": "AddSectionFace", "role": "concrete", "material": "C30",
            "point_ids": [_xyz(0, 0), _xyz(400, 0), _xyz(400, 600), _xyz(0, 600)]}),
        "circle": lambda: apply("circle", {
            "op": "AddSectionFace", "role": "steel", "material": "S355",
            "center_id": _xyz(600, 300), "radius_mm": 50}),
        "polygon": lambda: apply("polygon", {
            "op": "AddSectionFace", "role": "void", "material": None,
            "point_ids": [_xyz(100, 400), _xyz(300, 400), _xyz(200, 500)]}),
        "hole": lambda: apply("hole", {
            "op": "AddFaceHole", "face_id": created["rect"],
            "point_ids": [_xyz(100, 100), _xyz(200, 100), _xyz(200, 200)]}),
        "cover": lambda: apply("cover", {
            "op": "SetCover", "face_id": created["rect"], "cover_mm": 25,
            "tie_diameter_mm": 10, "bar_diameter_mm": 16}),
        "bar": lambda: apply("bar", {"op": "AddBar", "x_mm": 60, "y_mm": 60, "designation": "Ø16"}),
        "undo": document.undo,
        "redo": document.redo,
        "delete": lambda: apply("delete", {"op": "Delete", "entity_ids": [created["bar"]]}),
        "template": lambda: apply("template", {
            "op": "AddSectionTemplate", "template": "rect_column", "template_params": _COLUMN}),
        "delete-template": lambda: apply("x", {"op": "Delete", "entity_ids": [template_id]}),
        "undo-delete": document.undo,
        "explode": lambda: apply("x", {"op": "ExplodeSectionTemplate", "template_id": template_id}),
    }  # fmt: skip
    steps = {cast(str, s["label"]): s for s in cast(list[Json], out["steps"])}
    n_changes = 0
    for label, step in steps.items():
        if label in expected:
            expected[label]()
            n_changes += 1
            assert step["changeIsDraft"] is True, label  # onChange carried the v2 draft
        assert step["draft"] == section_draft(document, version=2), label
        assert step["changes"] == n_changes, label
    assert created["template"] == template_id

    # Invariant 10: the server's lock, shown by name; the client checked nothing itself.
    for label in ("hole-on-child", "delete-child"):
        assert steps[label]["error"] == "TEMPLATE_LOCKED", label
        assert cast(str, steps[label]["prompt"]).startswith("Refused: "), steps[label]["prompt"]
        assert "section template" in cast(str, steps[label]["prompt"]), steps[label]["prompt"]
    props = cast(list[str], steps["select"]["props"])
    assert props[0] == f"Template #{template_id} (rect_column v1) · locked", props
    assert "b = 400" in props and 'bar = "Ø20"' in props, props
    # Delete on a child took the subtree; Explode kept every child id and freed it.
    template_draft = cast(Json, steps["template"]["draft"])
    children = _ids(template_draft) - _ids(cast(Json, steps["delete"]["draft"]))
    assert children and not children & _ids(cast(Json, steps["delete-template"]["draft"]))
    exploded = cast(Json, steps["explode"]["draft"])
    assert _ids(exploded) == _ids(template_draft)
    assert cast(Json, exploded["section"])["templates"] == []
    # Invariant 9: each change, and the opening scene, is followed by `draft` at version 2.
    log = [(json.loads(r["req"]), r["ok"]) for r in cast(list[Json], out["requests"])]
    for i, (request, ok) in enumerate(log):
        if request["action"] != "draft" and ok:
            assert log[i + 1][0] == {"action": "draft", "version": 2}, (i, request)
    sent = {json.dumps(r["op"]["op"]) for r, _ in log if r["action"] == "apply"}
    assert '"EditSectionTemplate"' not in sent  # the client never re-expands a template
