# Phase 21: shared surfaces and runtime (track F)

Branch `phase/21-shared-surfaces`. Plan: docs/REMAINING_WORK.md §8 (F1–F6), brief in docs/PHASE_PLAN_16.md §5.

**Verdict: PASS with exceptions.** All six tasks shipped with tests (`tests/test_shared_surfaces.py`). The memory
(−83.8 %), LOD, doorway and lightmap gates are met. Texel density went up on the houses but down on 20 of the 26
small modules, and the workshop collider has 218 hulls, not 8 or 24.

The M2 milestone re-run of all ten MODULAR_HOUSE_PACK gates was not done (see "Not done").

## What shipped

| task | change | class |
|---|---|---|
| F1 | pack trim sheet: `packs/NAME.yaml: atlas: {size, density}`; members map onto one shared texture (`trim.py`) | FEATURE |
| F2 | material `archetype: vertex`: colour baked into `COLOR_0`, no texture; `VERTEX_COLOR_MIXED` validator | FEATURE |
| F3 | `{type: clean, weld_distance: 0.0005}` merges by distance; `GEO_DUPLICATE_SURFACE` finds unwelded copies | FEATURE + VALIDATION GAP |
| F4 | the three houses export `lods: [0.5, 0.25]`; `LOD_SILHOUETTE` thresholds are 0.95 for LOD1, 0.90 beyond | FEATURE |
| F5 | `collision: {mode: hulls, max, exclude}`: multi-hull decomposition that keeps openings open (`export/collision.py`) | FEATURE |
| F6 | lightmap UVs (`TEXCOORD_1`) per profile (`unity`, `unreal`) or `uv: {lightmap: true}`; `lightmap_uv` validator | FEATURE |

### F1: the trim sheet

Each pack material owns one horizontal strip of the texture, at full width and `size / n` pixels tall.

**How faces map.** A member's faces are grouped by plane and projected onto that plane, so slopes do not stretch.
- **U** follows the part's long axis at `density` px/m, so wood grain follows the timber.
- **V** spans the strip. A face taller than its strip is scaled to fit and reported as `UV_TEXEL_DENSITY`. None of the three houses triggers it.
- U wraps (sampler `wrapS: REPEAT`). The renderers wrap U too.

**How the texture is made.** The strip texture is the material recipe evaluated on a flat patch, the same for every member. Every export therefore writes byte-identical image data named `{pack}_trim_{key}`, so an engine stores one copy.

`packs/cozy_house.yaml` uses `atlas: {size: 2048, density: 128}`.

**Limitation.** Edge wear and grime that depend on a part's own edges are not on a trim sheet; they need a per-asset bake.

### F5: multi-hull collision

How the decomposition works:
- **Splitting.** Every part starts as its own convex hull. A non-convex closed part (a wall infill around a doorway) is first halved along its longest side by manifold booleans, until each piece's hull is at most 10 % empty (6 levels).
- **Merging.** Neighbouring clusters merge cheapest first, where the cost is the added empty volume.
- **Openings stay open.** A merge is refused when its hull would cover more than 6 probe points of empty space. The probe grid has a step of max(0.15 m, diagonal / 80) and is indexed by bounding box. So openings stay open even when that leaves more than `max` hulls.
- **Excluded parts.** `exclude` leaves out parts such as a door leaf that swings open.
- **LOD files.** LOD files reuse LOD0's collision, so the decomposition runs once per export.

Found and fixed on the way:
- **BUG:** `backend.convex_hull` crashed on some hulls with `No module named 'networkx'`. trimesh repairs hull winding through networkx, which is not a dependency.
  - Collision proxies now come from `backend.collision_hull`: Qhull directly, with faces wound outward.
  - Flat point sets use joggled Qhull, and a 1 mm box when even that fails.
  - Modelling keeps `convex_hull`: a first try that replaced it everywhere changed golden geometry (vertex order, and hand_cart's volume by 1.4 %).
- **Too slow:** the first decomposition took 62 s on the workshop, because every merge test scanned every probe. A grid lookup by index range now gives the same 218 hulls in 16.6 s; the whole export with LODs takes 44 s.
- **Doorway partly blocked:** at a 50 % piece tolerance the infill above the door left a hull reaching 0.5 m into the doorway, so only 0.8–1.85 m of the 0.66–2.40 m opening was clear. The 10 % tolerance clears it fully.

### F6: lightmap UVs

- **Layout.** Every part, authored ones included, is charted on its own and packed without overlap. Regions are sized by area, so the lightmap texel density is uniform.
- **Resolution.** `uv.lightmap_resolution` defaults to 1024. Padding is at least 4 px.
- **Export.** The exporter writes `TEXCOORD_1` with the same v flip as `TEXCOORD_0`.
- **Validator `lightmap_uv`:**
  - `LIGHTMAP_UV_MISSING` (error);
  - `LIGHTMAP_UV_OVERLAP` (error, above 0.2 % of the used area, or outside 0..1);
  - `LIGHTMAP_UV_DENSITY` (warning, above 2× across parts);
  - metrics `lightmap_uv_overlap`, `lightmap_uv_utilization`, `lightmap_texel_ratio`.
- **LOD files.** They reuse LOD0's atlas and carry no `TEXCOORD_1`. Bake lighting on LOD0.

## Gates

| gate | target | measured | met |
|---|---|---|---|
| F1 texture memory (26 modules + 3 houses, base + ORM, mips) | ≥ 60 % less | 263.3 MB → 42.7 MB: **−83.8 %** (29 atlases → 1 shared sheet) | yes |
| F1 texel density | equal or better | houses 33.7–48.8 → **128 px/m**; modules median 143 → 128 px/m (20 of 26 were above 128, range 104–187) | **in part** |
| F1 review sheets show no seams | — | `phase21/evidence/house_{townhouse,workshop}_trim.png`: no visible seams; 0 UV warnings on the houses | yes |
| F2 vertex colours | `COLOR_0`, Godot import OK | `COLOR_0` on every primitive, no image, base colour white; Godot reports `vertex_color` | yes |
| F3 merge by distance | weld + duplicate detection, fixture tests | a 0.2 mm-offset copy: 24 → 12 triangles after `weld_distance: 0.0005`; an unwelded copy is reported | yes |
| F4 LOD silhouette (worst of 4 views) | LOD1 ≥ 0.95, LOD2 ≥ 0.90 | cottage 0.995 / 0.964; townhouse 0.990 / 0.945; workshop 0.996 / 0.969 | yes |
| F5 walkable doorway | ray through the door passes | both workshop doors clear from 0.7 to 2.3 m; the wall beside and above blocks | yes |
| F5 Godot import | collider count | `--target godot`: 218 StaticBody3D, 218 ConvexPolygonShape3D, 0 import errors | yes |
| F5 hull count | `max: 8` (plan) | 218 (`max: 24` asked; refused merges keep openings open) | **no** |
| F6 lightmap UVs | overlap 0, texel ratio ≤ 2× | park_bench / storage_chest / torch_bracket (unreal): overlap 0.0, ratio 1.0, utilisation 38–55 % | yes |
| F6 engine import | UV1 present in Godot | park_bench_unreal: 2 of 2 visible surfaces carry `ARRAY_FORMAT_TEX_UV2` | yes |

## Golden

The geometry of no golden asset changed. Collision proxies and texture coordinates are not part of the golden signature.

## Not done

- **M2 milestone:** the full MODULAR_HOUSE_PACK gate re-run (10 gates) was not repeated; this phase measured the gates it changes.
- **Small modules** lose texel density on the shared sheet. Raising `density` to 160 would need a 4096 sheet or fewer strips.
- **Collision hull count:** a wall with many openings stays many hulls. A real VHACD-style decomposition would cut the count; it is in the backlog.
- **Unity and Unreal** lightmap import is by convention: `TEXCOORD_1` is what both importers read for lightmaps. It is not tested in those engines.
