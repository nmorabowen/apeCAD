# ADR 0003 — Python document is the public language; web GUI is a client

**Status:** Accepted (2026-08-14)

## Context

apeGmsh, apeSteel, Studio, and coding agents already speak Python.
apeGmsh’s Qt GUI was painful. That pain is a **GUI-toolkit** problem,
not evidence that Python is the wrong language for geometry documents.
The user is willing to compile or use JIT if it wins, and is not a GUI
specialist. Chili3D / ArcCAD show that interactive 3D sketch UIs are
at home in a web canvas.

Two layers were being collapsed into one language choice.

## Decision

Split the stack:

1. **Public authoring language = Python 3.11+.** The document, ops API,
   and bridges are this package. Agents write Python. `to_gmsh` /
   `to_frame` stay in-process with the rest of ape*.
2. **Scratchpad GUI = a thin web client** (TypeScript + Three.js when
   it exists). It emits ops at the Python API. It does not own
   geometry, undo, or labels.
3. **Compiled kernels** (OCCT, Manifold, Rust, C++) are allowed only
   **behind** the Python façade, and only when a feature must run in a
   pointer loop (snap at 60 fps, live boolean, constraint drag). v0
   has no such feature.
4. TypeScript is not the spatial language. Qt/PySide is not the
   default apeCAD GUI (leave Qt in Studio, where picking FEM already
   lives).

## Alternatives rejected

| Rejected | Why |
|---|---|
| TypeScript as the core | Splits agents and apeGmsh from the draft |
| C++/Rust as the public API | Slow iteration; agents do not author it |
| Python + Qt scratchpad | Replants the apeGmsh GUI seed |
| PyPy / JIT as the plan | Fights binary extensions; solves the wrong loop |

## Consequences

`src/apeCAD/` stays a Python package. A future `scratchpad/` (or similar)
is a client. Performance work is feature-gated: compile the pointer
loop, do not rewrite the document layer.
