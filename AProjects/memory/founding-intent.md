# Founding intent

apeCAD is a **spatial scratchpad**: a three-dimensional napkin.

Humans and agents put down lines, boxes, and labels so they do not have to
describe a complex object in paragraphs. That draft is the explanation. If
the draft is clean enough to realize as mesh or as a steel frame, that is a
bonus — not the definition of success.

## Is

- A standalone Python library with its own document and operations API.
- A spatial language agents can read and write.
- A service to apeGmsh, apeSteel, and later apeConcrete.
- Simple, versatile, and small.

## Is not

- SolidWorks, FreeCAD, Chili3D, or a parametric mechanical CAD suite.
- A replacement for the apeGmsh geometry session.
- A Studio CAD mode. Studio picks and shows; it does not author.
- A second solid kernel (no NumPy CSG, no OCCT in v0).

## Audiences

| Who | How they use apeCAD |
|---|---|
| Human | Sketches a draft so the model can be explained spatially |
| Agent | Reads/writes the same document, then authors the apeGmsh script |
| apeGmsh | Realizes labeled geometry when the draft is worth meshing |
| apeSteel | Consumes nodes, member axes, lengths, section ids |
| Studio | Displays and selects by name; never write-backs CAD |

Ratified by [ADR 0002](../adrs/0002-spatial-scratchpad.md).
