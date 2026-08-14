# Coupling map

apeCAD is a **producer of intent**. Other ape* libraries consume it.
Nothing in apeCAD should import apeGmsh or apeSteel at runtime in v0
unless a dedicated bridge extra is opted into later.

```
Cursor (human + agent)
        │  Python ops API
        ▼
   apeCAD Document          ← standalone SoT for the draft
        │
        ├─ to_gmsh(g)       → apeGmsh session (labels + OCC builders)
        ├─ to_frame()       → apeSteel (nodes, axes, section ids)
        └─ snapshot         → Studio host (pick / show by name)
```

| Consumer | Contract | Notes |
|---|---|---|
| **apeGmsh** | Labels + points/curves/faces/solids realized through `g.model.geometry` | Do not hand STL and hope Gmsh heals it. |
| **apeSteel** | Frame graph in N-mm-tonne-s | apeCAD stores mm internally ([ADR 0006](../adrs/0006-one-source-of-truth.md)). |
| **Studio** | Names-first selection envelope | Studio never write-backs the document ([ADR 0005](../adrs/0005-studio-is-consumer.md)). |

apeGmsh `.py` scripts remain the source of truth for **analysis**.
apeCAD is the source of truth for the **spatial draft**. An agent may
read the draft and write the script; the two files are not the same object.
