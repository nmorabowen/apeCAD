# Glossary

| Term | Meaning here |
|---|---|
| **Scratchpad** | The spatial napkin. A draft humans/agents draw to explain a 3D object. |
| **Document** | The in-memory Python object that *is* the draft. Source of truth. |
| **Ops / operations** | Typed commands (`AddLine`, `AddBox`, `Tag`, …) that mutate the document. |
| **JSON scene** | Serialization of the document. A file format, not a second editor. |
| **Kernel** | A geometry engine (OCCT, Manifold, Gmsh OCC). apeCAD v0 has none. |
| **Realize** | Translate the document into apeGmsh geometry or an apeSteel frame. |
| **Scratchpad GUI** | Optional drawing client. Emits ops; does not own geometry. |
| **Studio** | `apeGmsh.studio`. Pick/show/refresh host. Not a modeller. |
| **Label** | Stable name on an entity. The handle agents and Studio use. |
| **Frame graph** | Nodes + members + section ids for apeSteel. |
| **Intent** | What the draft means (a 6 m beam, a slab box), not a tessellation. |
| **Section mode** | RC section entities in the same document (ADR 0024). Intent only; apeConcrete owns the mechanics. |
| **ConcreteFace** | One closed CCW concrete outline, role `solid` (v1 allows exactly one). |
| **WallLeg** | A wall axis segment with thickness and its horizontal web steel; belongs to a face. |
| **Bar** | A longitudinal bar: its own Point, a diameter, and a designation from the closed vocabulary. |
| **Hoop** | A closed tie stored as the strict CCW convex hull of bar ids (P2). |
| **Crosstie** | A tie between two bars, with its hooks (`135-135` or `135-90`). |
| **CoverGuide** | Drawing aid that offsets a face by cover, tie and bar size; not read by apeConcrete. |
| **Section draft** | `apeCAD.section-draft` v1: ops log + derived `section` block ([spec](../specs/section-draft.md)). |
| **Section seed** | The `section` block with indices instead of ids; how older sections come back as ops. |
| **Transport** | `scratchpad.transport.handle`: a pure request → response over the whole ops log (ADR 0026). |
