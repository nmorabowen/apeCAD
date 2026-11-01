# Spec — `apeCAD.section-overlay` v1

**Status:** Implemented in the render tool (2026-11-01); the section client is stage C2-S2
**ADRs:** 0024, 0025, 0026, 0028, 0031, 0041

The one text of the results-overlay contract (ADR 0041 decision 1). A host (apeSection,
ape-web-tools) builds an overlay from results it computed and hands it to the section
client (`setOverlay`, ADR 0041 decision 2) or to the render tool (`render(overlay=...)`,
decision 3). apeCAD only draws it: an overlay has no meaning beyond "draw this". apeCAD
never stores it in the ops log, the draft or the seed (decision 1), and never posts it to
the transport (decision 4).

## The contract

```
{ "schema": "apeCAD.section-overlay", "version": 1, "units": "mm",
  "revision": <int >= 0>,                       # the document revision it was computed from
  "layers": [{"id": "<non-empty, unique>", "label": "<text>", "visible": true|false,
              "scale": null | {"kind": "sequential"|"diverging"|"categorical",
                               "domain": [lo, hi] | [lo, mid, hi] | ["<category>", ...],
                               "colors": ["<colour>", ...], "unit": "<text>",
                               "title": "<text>"},
              "primitives": [<primitive>, ...]}] }

<primitive> = <shape> + exactly one of {"style": <style>} or {"value": <number|category>},
              + optional "ids": [<entity id>, ...]
<shape> = {"kind": "polygon", "ring": [[x,y], ...], "holes": [[[x,y], ...], ...]}  # >= 3 points each; holes optional
        | {"kind": "circle", "center": [x,y], "radius": <mm > 0>}
        | {"kind": "polyline", "points": [[x,y], ...]}                             # >= 2 points
        | {"kind": "point", "at": [x,y]}
        | {"kind": "label", "at": [x,y], "text": "<text>"}
<style> = {"stroke": <colour>|null, "fill": <colour>|null, "width_px": <number > 0>,
           "opacity": <0..1>}                                                    # every key optional
<colour> = "#rgb" | "#rrggbb" | a design token: "--text", "--muted", "--accent", "--signal",
           "--ink-edge", "--ink-rebar", "--ink-concrete", "--ink-section-guide", "--fill-concrete"
MAX_OVERLAY_PRIMITIVES = 200000                 # over all layers; above it refused, never truncated
```

SHA-256 of the block's content: the text between the fences, with LF line endings and a
final newline (the ADR 0025 rule).

```text
29f595b38d823ed2363209c35084e1ba251f385ef7658db4932e5652a7497c3b
```

A pasted copy is the contract only when it hashes to this value: read the text between the
fences, normalise line endings to LF, ensure one trailing newline, and run `sha256`.
`tests/test_render_overlay.py` pins it.

## Rules

These rules sit outside the hashed block, so the contract is unchanged by them. The
validator is `apeCAD.render.overlay.parse_overlay`. The section client (stage C2-S2) mirrors
it and must agree with it on every case in `tests/fixtures/section_overlay/`.

- **Closed shape.** A reader refuses, naming the field: an unknown key at any level, a
  missing required key, a wrong type, a `bool` where a number or an id is expected, and a
  number that is not finite. Any new field or value is `version` 2. This differs from
  section-draft rule 6, which allows additive v1 fields: a reader that drew an overlay while
  ignoring a field it did not know could show a result wrongly, which is worse than refusing.
- **Refusals** carry a `code` and the `path` of the refused field: dotted keys and `[i]`
  list indices from the root `overlay`, e.g. `overlay.layers[0].primitives[2].style.fill`.
  - A field with a wrong type or value is its own path.
  - An unknown key, or a missing required key, is the path of that key
    (`overlay.layers[0].scale.title`). Unknown keys are reported before missing ones,
    each the first in sorted order.
  - A rule over several fields of one object names the object: both or neither of
    `style` and `value` names the primitive; a style that paints nothing names the
    `style`. A repeated layer id or category names the later occurrence. A categorical
    scale whose colour count differs from its categories names `colors`. The cap names
    `overlay.layers`.
  - A primitive whose `kind` is missing or unknown names its `kind`, before any other key.
  - Each fixture case has exactly one fault. With several, which one is named is not
    specified. The message is for people: it starts with the path, and its wording is
    free.
- **Integers** (`version`, `revision`, `ids`) are defined by value: a finite number with
  no fractional part. `1.0` is the integer 1, as `JSON.parse` reads it, and a reader
  normalises it to an integer; `1.5` is refused.
- `schema`, `version` and `units` are exactly `"apeCAD.section-overlay"`, `1` and `"mm"`.
- **Coordinates** are world millimetres in the section plane (x right, y up, z = 0), the
  frame of the section-draft. The render tool draws an overlay on the `top` view only, and
  refuses one on any other view.
- **Layers** draw in list order, each above the one before. `id` is unique across the
  overlay. A layer with `visible: false` is validated but not drawn, and neither is its
  legend. The client's layer list shows `label`; the render tool writes it as `data-label`.
- **Paint.** A primitive carries exactly one of `style` or `value`. Both, or neither, is
  refused.
  - With `style`, `polygon` and `circle` take `fill`, `stroke` or both; `polyline` takes
    `stroke` only; `point` and `label` take `fill` only. A paint key the kind does not take
    is refused, and so is a style that paints nothing. `width_px` (default 1) is the stroke
    width in screen pixels. `opacity` (default 1) applies to the whole primitive.
  - With `value`, the layer must have a `scale`. The colour fills a `polygon`, `circle`,
    `point` or `label`, and strokes a `polyline` at 1.5 px.
- **Marks.** A `point` is a dot of 2.5 px radius at `at`. A `label` is text in the working
  font whose baseline starts at `at`. A `circle`'s radius is millimetres, so it scales with
  the view.
- **Colours** are `#rgb` or `#rrggbb` in either case, written back as lower-case `#rrggbb`,
  or one of the tokens above. The tokens name the ADR 0031 roles of `static/css/app.css`.
  The render tool resolves a token to its light-theme value, because the SVG is drawn on
  white; the client resolves it from the live theme. Anything else (`#rrggbbaa`, `red`,
  `rgb(...)`, `var(--x)`, an unknown token) is refused.
- **Scales.** `colors` has at least 2 entries.
  - `sequential`: `domain = [lo, hi]` with `lo < hi`. The colours are evenly spaced stops
    from `lo` to `hi`.
  - `diverging`: `domain = [lo, mid, hi]` with `lo < mid < hi`, and an odd number of colours,
    at least 3. The middle colour sits at `mid`, and each half's colours are evenly spaced
    stops over its half of the domain.
  - `categorical`: `domain` is a list of distinct strings, one per colour. A `value` not in
    `domain` is refused.
  - A numeric value outside the domain takes the end colour (it is clamped). Between two
    stops, at fraction `t`, each sRGB channel is `floor(c0 + (c1 - c0) * t + 0.5)` (8-bit,
    no gamma conversion). An SVG gradient interpolates the same way, so the legend's gradient
    matches the fills.
  - A number `value` on a categorical scale, or a string `value` on a numeric one, is
    refused.
- **Text** (`label.text`, a layer's `id` and `label`, and a scale's `unit`, `title` and
  categories) is plain text. The render tool escapes it through `render/svg.py::clean_text`.
  The client sets it through `textContent` only (ADR 0026 decision 4).
- **Ids** are non-negative integers that link a primitive to apeCAD entities, for hover and
  highlighting. An id the document does not have is not an error, because an overlay may be
  stale. The render tool writes them as `data-ids="1 2 3"`.
- **Size cap.** More than `MAX_OVERLAY_PRIMITIVES` primitives over all layers, visible or
  not, is refused (`TOO_LARGE`), and nothing is drawn. The count is checked before any
  primitive is read. An overlay is never truncated.
- **Staleness** belongs to the client (ADR 0041 decision 2), which knows the live revision.
  The render tool does not judge it. It draws the overlay as given and returns
  `overlay_revision` next to the envelope's `revision`, so the caller can compare them.

## Render tool

`render_svg(document, ..., overlay=...)` and `render_png(...)` take the overlay as a parsed
`Overlay` or as its JSON object. The MCP `render` tool and
`python -m apeCAD.cli render FILE --overlay OVERLAY.json` take the JSON object. A refusal is
`INVALID_ARGUMENT` (`TOO_LARGE` for the cap), with a message that names the field.

In the SVG, the overlay is one `<g class="overlay" data-revision="N">`. It sits above the
section and sketch geometry and below the annotation, the highlight and the labels. Each
drawn layer is a `<g class="overlay-layer" data-layer="id" data-label="label">`. Each visible
layer with a scale adds a legend at the top right (`<g class="overlay-legend"
data-layer="id">`): the title and unit, then a gradient bar labelled with the domain values
(numeric scales), or a swatch per category. The fit, the scale and `extents_mm` are the
document's: the overlay never moves the view.

## Fixtures

`tests/fixtures/section_overlay/` holds the shared cases, the Python/JS parity oracle for the
client (stage C2-S2):

- `valid/*.json` are overlays that must be accepted.
- `invalid.json` is a list of `{"case", "overlay", "refusal": {"code", "path"}}`. Each
  reader must refuse the overlay with exactly that `code` and exactly that `path` (rule
  "Refusals"). The fixtures carry no message text: wording is free.
- `colors.json` lists scale lookups `{case, scale, value, color}` that both readers must
  reproduce exactly. Each expected colour was worked by hand from the formula above.
- JSON cannot carry a non-finite number or the cap plus one in a file of sensible size, so
  `tests/test_render_overlay.py` builds those cases in code. The client's tests must do the
  same.

The golden SVG is `tests/fixtures/render/section_overlay_top.svg`.
