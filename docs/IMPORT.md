# Import, modify and repair (Phase 11)

## Question

Can an agent take an **existing** game asset, then import it, understand its parts, assign
semantics, repair technical problems, modify geometry, improve or replace the surface, and export,
without losing what the file already had and without framework changes? Imported meshes do
**not** regain procedural intent. The question is whether they can be worked on honestly next to
native parts.

## Research: four real CC0 assets through the Phase 10 pipeline

The test files are Khronos glTF sample models, all CC0 1.0: Lantern (Microsoft), SheenChair
(Wayfair), BoomBox and WaterBottle (Microsoft). They are typical production assets: PBR texture
sets up to 2048², normal maps, multiple materials, open meshes, mirrored UVs, and non-metre units.

| Finding | Evidence | Class |
|---|---|---|
| **Materials and textures are dropped.** Every import got one grey `imported` material, so re-exporting destroys the asset's look | 4/4 assets: `materials 1`; Lantern's 2048² base/ORM/normal/emissive set, SheenChair's 4 materials | **CAPABILITY, foundational** |
| **Authored overlapping UVs are an error** that blocks export | SheenChair 3.8% and WaterBottle 0.3% `UV_OVERLAP` (mirrored/stacked islands are normal practice) | VALIDATION (false positive for authored UVs) |
| **No repair ops** for imported defects | Lantern: `GEO_DEGENERATE_FACES` error on one piece; nothing can remove the faces | CAPABILITY |
| **Decimate destroys authored UVs** (resample → corners invalidated) | "reduce triangle count" on any textured import loses its texture mapping | CAPABILITY |
| **Units are unchecked on import** | Lantern 25.7 m tall; BoomBox 2 cm; the scale warning only fires below 1 cm or above 200 m | DISCOVERY / ERGONOMICS |
| **Split pieces lose node names** | `piece_01..17` for Lantern, whose nodes are `LanternPole_Body/Chain/Lantern` | DISCOVERY |
| Budgets: imported assets exceed the default profile | SheenChair 39,936 tris vs 5,000 | expected: the agent picks a profile or decimates |

## Design

### 1. Authored materials: pass-through, not re-baked

`sw import` writes each glTF material as an **`authored`** material:

```yaml
materials:
  lanternpost_mat:
    archetype: authored
    textures: {base_color: source/textures/lanternpost_mat_base_color.png, metallic_roughness: ...,
               normal: ..., occlusion: ..., emissive: ...}
    color: "#ffffff"          # factors, as in the file
    roughness: 1.0
    metallic: 1.0
    emissive: "#ffffff"
    alpha_mode: OPAQUE
```

- Parts with an authored material keep their **authored UVs** exactly. They take no space in the
  asset atlas, are not baked, and export with their own texture set, like the original.
- Re-baking into the atlas would resample, lose normal maps, and cost resolution for no gain.
- Consequence: an asset mixing authored and native materials exports two texture sets. The
  report states this, and Phase 12 decides policy on draw calls and material counts.
- To **change** the look of an imported part, the agent assigns a native archetype material.
  That part then bakes into the atlas, using its authored UVs as the chart layout, exactly as
  `mesh_file` parts already do.
- If an op drops the authored UVs of a part that has an authored material, the part can no longer
  be textured. `TEX_UV_SOURCE_MISSING` becomes an **error** for authored materials.
- Texture paths are sandboxed to the asset directory, like image layers.

### 2. Validation of authored UVs

Overlap, out-of-bounds (tiling) and texel density checks skip parts that use authored materials.
Their UVs are the author's, and the atlas is not involved. Overlap coming from authored UVs used
as atlas charts is a **warning** (mirrored islands share texels), not an error.

### 3. Repair: a `clean` op

`{type: clean, weld: true, degenerate: true, duplicates: true, winding: true, fill_holes: false}`
does the following:
- welds coincident vertices;
- removes zero-area and duplicate faces;
- makes winding consistent and outward (closed shells);
- optionally fills holes.

Removed faces take their attributes with them. Flipped faces keep theirs, with corners reordered.
Filled faces get region `cut` and no UVs. Topology class: `rebuild`.

### 4. Decimate keeps authored UVs

After simplification, each new face takes its UVs from the source triangle nearest its centroid:
the three corners are projected onto that triangle's plane and mapped through its UV frame. The
chart stays consistent per face, so no UV smears across seams. UVs become **transferred**, not
invalidated. Faces also inherit labels (material, region) from that source triangle.

### 5. Import ergonomics

- Split pieces are named `<node>_<n>`, not `piece_<n>`.
- The importer prints each part's size and a scale hint when the asset is below 5 cm or above
  50 m ("`--scale 0.01` if the file is in centimetres").
- It reports materials and textures found.

## Out of scope (stated honestly)

- Recovering procedural intent from meshes.
- Re-topology.
- UV unwrapping that preserves authored charts across heavy edits.
- KHR material extensions (sheen, clearcoat, transmission). These are not imported, and the report lists them.

## Predictions for the gate experiment (FRESH_AGENT_07, written before implementation)

The task: import two real assets, then repair, reduce, modify, re-material one part, add collision and
a native part, make a variant, and export.

| # | Prediction |
|---|---|
| I1 | Textures survive the import → export round trip (Khronos-clean, same texture count per authored material) |
| I2 | The agent renames pieces from renders and uses `--split` where it needs to address sub-parts |
| I3 | Decimation to a budget keeps the texture mapping visibly correct |
| I4 | Replacing a handle/part means deleting an imported piece and adding a native part: works, with a `measure` for fit |
| I5 | The agent is surprised that a changed material is baked while untouched parts keep their textures (two texture sets). The report must explain it |
| I6 | 0 framework changes (the gate) |

## Implementation status (before FRESH_AGENT_07)

Implemented as designed: authored pass-through materials (importer, surface, bake, validation,
export, preview renders), the `clean` op (winding by breadth-first search over shared edges, hole
fans), UV-preserving `decimate` (corner transfer through one source face; `resample` corners
are now *transferred*), node-named pieces, and unit/extension hints. Tests: `tests/test_import.py`,
which uses its own minimal glTF reader, independent of trimesh.

### A bug this phase found: every exported texture was mirrored vertically (Phase 8 to 10)

Internal UVs are v-up (trimesh flips v on load), but glTF's v runs down from the image's top row.
The exporter wrote v unchanged, so **every textured GLB since Phase 8 sampled its atlas mirrored**
in engines. Nothing that existed could see it:
- the Khronos validator checks structure, not appearance;
- the round-trip check re-imports through trimesh, which flips v back;
- our renderer uses internal UVs.

It surfaced when the authored-UV round trip was checked against the original file's raw accessors.
Fixed in the exporter; `test_exported_atlas_follows_the_gltf_uv_convention` samples the exported
image as an engine would. All 33 committed exports were re-exported.

**Lesson:** export correctness needs at least one check that reads the file with the target's
conventions, not with the library we imported through.
