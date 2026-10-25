# Coupling map

apeCAD is a **producer of intent**. Other ape* libraries consume it.
Nothing in apeCAD should import apeGmsh or apeSteel at runtime in v0
unless a dedicated bridge extra is opted into later.

```
Cursor / Agents (human + agent)
        │  Python ops API, MCP (`apeCAD.mcp`), CLI (`apeCAD.cli`), or HTTP transport
        ▼
   apeCAD Document          ← standalone SoT for the draft
        │
        ├─ to_gmsh(g)                   → apeGmsh session (labels + OCC builders; not implemented)
        ├─ to_frame()                   → apeSteel (nodes, axes, section ids; implemented)
        ├─ section_draft() / from_seed  → apeConcrete (`apeCAD.section-draft` v1 & `apeCAD.section-seed` v1; implemented)
        ├─ transport.handle / assets    → ape-web-tools HA-04 (`apeCAD.scratchpad.transport.handle`, `section_assets`; implemented)
        ├─ render_svg / render_png / dxf → SVG, PNG (`apeCAD[png]`), DXF (`apeCAD[dxf]`; implemented)
        └─ snapshot                     → Studio host (pick / show by name)
```

| Consumer | Contract | Notes |
|---|---|---|
| **apeGmsh** | Labels + points/curves/faces/solids realized through `g.model.geometry` | Do not hand STL and hope Gmsh heals it (`to_gmsh` not implemented yet). |
| **apeSteel** | Frame graph in N-mm-tonne-s (`Document.to_frame()`) | Implemented. apeCAD stores mm internally ([ADR 0006](../adrs/0006-one-source-of-truth.md)). |
| **apeConcrete** | `apeCAD.section-draft` v1 (`apeCAD.section_draft.section_draft` / `document_from_draft`), `section` block only ([spec](../specs/section-draft.md), ADR 0025); writes `apeCAD.section-seed` v1 back (`document_from_seed`) | Implemented. Never imports apeCAD (its ADR-0025 D8); copies fixtures at a pinned apeCAD sha. |
| **ape-web-tools** | `apeCAD.scratchpad.transport.handle` behind `POST /api/cad/transport`; the 2-D client from `apeCAD.scratchpad.section_assets.client_files()` (ADR 0026) | Implemented. HA-04 Geometria tab; stores the draft in a run (its ADR-0006). |
| **Agents (MCP & CLI)** | `python -m apeCAD.mcp` (`apeCAD.mcp`) and `python -m apeCAD.cli` (`apeCAD.cli`) tools over the op catalog; `render` writes SVG or PNG (`apeCAD[png]`) and `export_dxf` writes DXF (`apeCAD[dxf]`) into apeWorkbench `pictures/` via `save_to` ([ADR 0028](../adrs/0028-agent-surface-mcp.md), [ADR 0034](../adrs/0034-dxf-export.md), [spec](../specs/agent-surface-mcp.md)) | Implemented (stages S1–S7, D5). Attach mode targets one instance by `/api/identity` (ADR 0019) and never falls back. |
| **Studio** | Names-first selection envelope | Studio never write-backs the document ([ADR 0005](../adrs/0005-studio-is-consumer.md)). |

apeGmsh `.py` scripts remain the source of truth for **analysis**.
apeCAD is the source of truth for the **spatial draft**. An agent may
read the draft and write the script; the two files are not the same object.
