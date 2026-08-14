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
