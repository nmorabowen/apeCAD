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

Pre-alpha (`0.0.0`). The package installs and exports `__version__`. The
product contract lives in [`AProjects/`](AProjects/README.md).

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
