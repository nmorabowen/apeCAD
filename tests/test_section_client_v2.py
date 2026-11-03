"""The 2-D client draws v2 (C5 record §3 "Client data" A and "Client drawing"; C5-S3).

The oracles come from outside the client: `render`'s drawables (C5-S1) on the 11 committed
v2 fixtures, the v2 draft's items (one projector), the v1 and v2 lints, and
`require_v1_expressible`. Each JS check runs the shipped modules under node, driven from here.
Record §4 invariants 1, 7 and 8, the scene's warnings, and a too-deep body over the live
transport. The pure painting oracles (3, 4, 12, 10^5 bars) are `tests/js/section-v2.test.mjs`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from threading import Thread
from typing import Any, cast

import pytest

from _section_fixtures import BUILDERS
from _section_fixtures_v2 import BUILDERS_V2, fixture_path_v2
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
