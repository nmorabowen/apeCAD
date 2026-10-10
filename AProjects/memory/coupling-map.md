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
        ├─ section_draft()  → apeConcrete reader (via ape-web-tools runs)
        └─ snapshot         → Studio host (pick / show by name)
```

| Consumer | Contract | Notes |
|---|---|---|
| **apeGmsh** | Labels + points/curves/faces/solids realized through `g.model.geometry` | Do not hand STL and hope Gmsh heals it. |
| **apeSteel** | Frame graph in N-mm-tonne-s | apeCAD stores mm internally ([ADR 0006](../adrs/0006-one-source-of-truth.md)). |
| **apeConcrete** | `apeCAD.section-draft` v1, `section` block only ([spec](../specs/section-draft.md), ADR 0025); writes `apeCAD.section-seed` v1 back | Never imports apeCAD (its ADR-0025 D8); copies fixtures at a pinned apeCAD sha. |
| **ape-web-tools** | `scratchpad.transport.handle` behind `POST /api/cad/transport`; the 2-D client from `section_assets.client_files()` (ADR 0026) | HA-04 Geometria tab; stores the draft in a run (its ADR-0006). |
| **Studio** | Names-first selection envelope | Studio never write-backs the document ([ADR 0005](../adrs/0005-studio-is-consumer.md)). |

apeGmsh `.py` scripts remain the source of truth for **analysis**.
apeCAD is the source of truth for the **spatial draft**. An agent may
read the draft and write the script; the two files are not the same object.
