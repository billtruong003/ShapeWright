# Game-ready production layer (Phase 12)

## Question

Can an exported asset enter a normal game-engine pipeline **without significant manual cleanup**?
"Normal" means the engine's own importer, with its documented naming conventions. That covers
physics, draw calls, LODs, pivots, normal maps and naming. Engine-specific logic stays out of the
geometry core.

## Research: every benchmark export imported by a real engine

`tools/engine/godot_check.py` runs **Godot 4.3's own importer**, headless, on each GLB and walks the
imported scene. Godot is the one engine that runs in a container; for Unity and Unreal, only their
documented conventions can be followed, not tested (stated below).

Baseline: 33 committed exports.

| Finding | Evidence | Class |
|---|---|---|
| Everything imports, at the right size, grounded | 33/33 imported, no import errors; sizes equal to `sw stats`; lowest point y = 0 | ✔ |
| **Draw calls = parts** | one mesh per part: fountain **806 surfaces**, roof 100, bridge 94, chest 46; a static prop wants ~1 per material | **PRODUCTION (foundational for games)** |
| **Collision naming is engine-specific; the default was Unreal's** | `UCX_` nodes import into Godot as **visible grey meshes** with no physics (11 phantom boxes on the chair) | **BUG for non-Unreal targets** |
| With the `godot` profile, bodies are created, but as **triangle-mesh** shapes | `-colonly` → `ConcavePolygonShape3D` ×11; our boxes/hulls are convex, and `-convcolonly` gives convex shapes (cheaper; required for dynamic bodies) | PRODUCTION |
| Normal-mapped materials export without tangents | Khronos `MESH_PRIMITIVE_GENERATED_TANGENT_SPACE` on imported assets (FA-07) | PRODUCTION |
| No LODs | nothing exported beyond LOD0 | CAPABILITY |
| Collision modes all-or-nothing | FA-07: no single hull, no per-part choice | CAPABILITY |
| Sockets arrive as empty nodes | markers present in the Godot scene | ✔ |

## Design

**Export targets** (profile `export.target`: `generic` | `godot` | `unity` | `unreal`) are an adapter
in `shapewright/export/targets.py`. The geometry model knows nothing about engines; a target only
decides names and packaging.

| | generic | godot | unity | unreal |
|---|---|---|---|---|
| Collision nodes | `COL_<asset>_<n>`, `extras.collision` (no engine auto-physics claimed) | `<n>-convcolonly` (convex) / `-colonly` (mesh) | `<asset>_<n>_collider` + `extras.collision` (glTF importers don't create colliders; the importer script must read the extras) | `UCX_<asset>_<nn>` (convex) |
| Static merge | off (part nodes, as before) | on | on | on |
| LODs | separate files `<asset>_LOD<n>.glb` | not exported: Godot generates LODs at import | separate files | separate files |

Only Godot's column is verified in-engine. The Unity and Unreal columns follow those engines'
documented import conventions and are **not** tested here.

- **Static merge** (`export.merge: by_material`): all parts that don't need their own transform are
  merged into one node `<asset>` with **one primitive per material**. Kept separate:
  - parts with a `pivot`;
  - parents of other parts, and their children (hinged lids, wheels);
  - parts tagged `separate`.

  Part identity survives in `extras.parts` as a triangle range per part and material. Draw calls =
  primitives, and the report and the `BUDGET_DRAW_CALLS` check use that count (`budget.draw_calls`).
- **Collision** modes: `none | single_box | box | hull | single_hull`, plus `parts: [...]` to limit
  which parts get proxies. Convex by construction, so targets name them convex.
- **Tangents**: primitives whose material has a normal texture get `TANGENT` (per-vertex,
  Lengyel's method, with handedness w).
- **LODs**: `export.lods: [0.5, 0.25]` writes decimated LOD files (decimation keeps UVs since
  Phase 11) and reports each LOD's silhouette agreement with LOD0 (IoU from 4 views).
  `LOD_SILHOUETTE` warns below 0.9.
- **Origin policy**: unchanged, already enforced (`placement: floor | wall | free`,
  `ASM_ORIGIN_OFFSET`). Godot confirmed floor props arrive grounded and centred.

## Predictions for the gate (written before implementation)

The gate: a fresh agent is asked to prepare a small prop set for a Godot project **and** for an
Unreal project. Every Godot export is checked in Godot.

| # | Prediction |
|---|---|
| E1 | The agent finds `export.target` via profiles or `sw caps`, and uses the `godot`/`unreal` profiles |
| E2 | In Godot every asset has physics bodies with convex shapes and no visible collision meshes |
| E3 | Draw calls per static prop ≤ materials + moving parts |
| E4 | A hinged or moving part keeps its own node and pivot (it is not merged) |
| E5 | LOD files are produced for the Unreal set; the agent does not check their silhouettes unless the report surfaces it |
| E6 | 0 framework changes |
