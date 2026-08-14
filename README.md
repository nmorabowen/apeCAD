# apeCAD

Spatial scratchpad and intent document for the ape* structural toolchain.

apeCAD is a **standalone Python library**. It is not a SolidWorks clone and
not a second Gmsh session. It exists so a human or an agent can put down a
three-dimensional draft — lines, boxes, labels — instead of describing a
building in paragraphs. Downstream libraries consume that draft:

- **apeGmsh** realizes geometry and mesh.
- **apeSteel** consumes the frame graph (nodes, members, section ids).
- **apeGmsh.studio** shows and picks; it does not author CAD.

The drawing window, when it exists, is a **client** of this package. The
Python document is the spatial language.

This repository is **private**.

## Status

Pre-alpha (`0.0.0`). The v0 `Document`, `to_frame()`, and a localhost
scratchpad are implemented. The product contract lives in
[`AProjects/`](AProjects/README.md).

```python
from apeCAD import Document

cad = Document()
a = cad.add_point(0, 0, 0, label="A")
b = cad.add_point(6000, 0, 0, label="B")
cad.add_line(a.entity_id, b.entity_id, label="beam_B1")
cad.add_box((0, 0, 0), (6000, 4000, 200), label="slab_L2")
print(cad.to_json())
```

## Scratchpad

```bash
python -m apeCAD
```

Opens `http://127.0.0.1:8765`. Draw lines and boxes on the XY plane
(z = 0). The canvas posts ops to the Python document. Save JSON from
the toolbar when you want a file snapshot.

```bash
python -m apeCAD --no-browser --port 8765
```

## Layout

```
src/apeCAD/          public Python package
tests/               pytest
AProjects/           project memory, ADRs, specs, guides
```

## Install (development)

```bash
git clone https://github.com/nmorabowen/apeCAD.git
cd apeCAD
pip install -e ".[dev]"
pytest
```

Requires Python ≥ 3.11.

## Project memory

Read [`AProjects/README.md`](AProjects/README.md) first. Architecture
decisions are append-only ADRs under [`AProjects/adrs/`](AProjects/adrs/README.md).
