# Cozy House modular kit (MODULAR_HOUSE_PACK_01)

This is a stylized medieval / cozy-fantasy half-timbered house kit. It has timber frames, cream plaster, stone footings and clay shingles.

Every module, and each of the three demo houses built from it, was generated from YAML sources by Shapewright. Nothing was hand-modelled.

The full experiment record, with findings, limitations and the verdict, is `docs/experiments/MODULAR_HOUSE_PACK_01.md` in the repository.

```
modular_house_pack/
├── README.md          this file
├── sources/           packs/cozy_house.yaml (source of truth), styles/, components/ (12 kit components + plank_top),
│                      assets/<module or house>/asset.yaml + uv.lock.yaml
├── materials/         materials.yaml (the 7 shared materials) + material_sheet.png
├── textures/          per-asset baked atlases: <asset>_basecolor.png, <asset>_orm.png (occlusion/roughness/metal)
├── modules/           26 module GLBs (+ _godot variants where exported)
├── demo_houses/       house_cottage / house_townhouse / house_workshop (.glb and _godot.glb)
├── renders/           hero renders per house, one contact sheet per module group, seam close-ups, stress-test renders
├── validation/        per-asset export reports (validator + Khronos glTF validator), seam-probe results
└── metrics.json       reuse, parameterization, runtime metrics
```

## Scale and grid

**Units and axes**
- 1 unit = 1 m. Y is up.
- A wall's outer face is the module's local +Z.

**Plan grid**
- `bay` = 2.0 m; a half bay is 1.0 m.
- Walls run along grid lines and are centred on them.

**Levels**
- Storey k has its deck top at `base_h + k·storey`, where `base_h` = 0.5 m and `storey` = 3.0 m.
- Level 0 = 0.5, level 1 = 3.5, level 2 = 6.5.

**Construction rule**

*Posts and walls*
- A `post` (0.26 m) stands on every grid node.
- A wall module fills the span between two posts: `bay − post` = 1.74 m wide.
- Neighbouring walls therefore never overlap, and a corner is just a post. No special corner wall is needed.

*Heights*
- Walls and posts start `sink` = 2 cm below the deck top, so they are embedded and never leave a gap.
- A wall module is `panel_h = storey − floor_t + sink` tall and ends under the next deck.
- A band beam fills the floor zone outside, between posts.

*Footings*
- Stone footings stop 2 cm below the ground deck top, so the two are never coplanar.

**Source of truth**
- All dimensions live in `sources/packs/cozy_house.yaml` (34 params, read-only in every member).
- Key values: `bay`, `storey`, `floor_t`, `base_h`, `post`, `timber` (0.18), `wall_t` (0.26), `plaster_t` (0.16), opening sizes, `pitch` (45°), `eave` (0.45), `verge` (0.3), shingle `course` and `tile_w = bay/6`.
- The derived values (`wall_h`, `panel_h`, `lv1`, `lv2`, `band_h`) are expressions, so changing `bay`, `storey` or `pitch` re-flows every module and house.

## Modules (26)

| group | modules |
|---|---|
| walls | `house_wall_plain`, `house_wall_window` (`size` 0 small / 1 standard / 2 tall, same head line), `house_wall_window_offset`, `house_wall_door`, `house_wall_shopfront`, `house_wall_half` (half bay), `house_wall_upper` (upper storey, window) |
| corners / framing | `house_corner` (post + footing), `house_post`, `house_beam_vertical`, `house_beam` (band beam), `house_brace` |
| floors / foundation | `house_floor` (1 bay × 1 bay), `house_floor_half`, `house_footing`, `house_steps` |
| roof | `house_roof_section` (1 bay of slope), `house_roof_end` (verge end), `house_gable` (gable infill + truss), `house_ridge`, `house_roof_eave`, `house_chimney` |
| openings | `house_window`, `house_door_frame`, `house_door`, `house_shutter` |

Contact sheets are in `renders/modules_<group>.png`. Per-module triangle counts range from 44 to 1,384 (median 272).

## Pivots (origins)

Every module GLB is exported with its origin as below. Values in parentheses are the measured bounds at default params.

| module kind | origin |
|---|---|
| walls (`house_wall_*`) | bottom centre on the wall's centre plane; the outer face is +Z (plain: x ±0.875, y 0…2.78, z ±0.131) |
| posts, `house_corner`, `house_beam_vertical` | grid node, bottom |
| `house_beam` (band beam) | beam centre (vertically centred, y ±0.114) |
| `house_floor`, `house_floor_half` | cell centre, deck underside (the deck spans y 0…`floor_t`) |
| `house_footing`, `house_chimney` | bottom centre |
| `house_steps` | bottom of the threshold edge; the flight runs out along +Z |
| `house_roof_section`, `house_roof_eave` | ridge line plumb at the eave-underside height; the slope runs down along +Z (section: z 0…2.625); the section spans one bay (x ±1.01) |
| `house_roof_end` | as the roof section, for the verge overhang beyond the gable |
| `house_ridge` | on the apex line |
| `house_gable` | bottom centre on the gable-wall centre plane; faces ±X |
| `house_window`, `house_door`, `house_shutter`, `house_door_frame` | bottom centre of the opening piece, centred on its own depth; the front is +Z |

## Snapping rules

- **Position.** Every piece is placed by its origin at grid arithmetic only: `x = i·bay`, `z = j·bay`, `y = level(k) − sink`. No hand offsets are required between kit pieces.
- **Rotation.** Walls use 0° (front), 180° (back), 90° (+x side) or −90° (−x side), so the outer face always points outward.
- **Roofs.** Place roof sections at `i·bay` along the ridge. The shingle bond (`tile_w = bay/6`) runs continuously across section seams.
- **Floors.** Place floors at cell centres.
- **Shared grid lines.** Where two blocks share a grid line (see `house_workshop`), place the shared posts and walls once. The wing's roof dies into the main block's wall.

## Materials

There are seven shared materials, defined once in the pack and read-only everywhere:

| material | used for |
|---|---|
| `timber` | structural timbers |
| `planks` | doors, shutters, floor decks |
| `plaster` | wall and gable infill |
| `stone` | footings, chimney, steps |
| `roof` | clay shingles |
| `glass` | glazing |
| `iron` | hardware |

- Material drift is zero by construction. No asset defines its own material.
- Exports merge by material. A house is 7 materials and 7 draw calls; a module is 1–4.
- Each asset bakes its own 1024² (houses larger) atlas into `textures/`: base colour plus ORM.
- The atlases are not shared between assets. See the limitations.

## Collisions

- Modules export a `single_box` collider.
- `house_roof_section` and `house_roof_end` use `single_hull` so the slope is walkable.
- The cottage and townhouse use one box. The L-shaped workshop uses one hull.
- These are exterior-prop colliders only: there is no interior collision. For walkable interiors, place the modules individually.

## Runtime

| house | triangles | parts merged | draw calls | GLB |
|---|---|---|---|---|
| cottage | 24,476 | 370 | 7 | 4.8 MB |
| townhouse | 33,042 | 571 | 7 | 5.9 MB |
| workshop | 45,080 | 725 | 7 | 6.6 MB |

- The Khronos glTF validator reports 0 errors and 0 warnings on every GLB.
- The `_godot.glb` variants imported cleanly in Godot 4.3 headless.

## Known limitations

- ~~Houses cannot place the module assets.~~ Closed in Phase 19: every house is built from module-asset instances (`asset: house_wall_window`); since FRESH_AGENT_13 the shared base is `house_foundation`.
- **Some offsets are hand-derived.** Shutters and the shop awning are positioned by hand-derived offsets (`wall_t/2 + 0.024`, `wall_t/2 − 0.027`), because an instance cannot measure another instance. They are pack-param expressions, but they had to be repaired once after the wall's stud depth changed.
- **Atlases are per asset, not a shared trim sheet.** A game using many modules pays per-module texture memory.
- **No interior.** There is no interior geometry or interior collision, and upper floors have no stairs.
- **Seam checking is an experiment tool.** The standard validator does not check z-fighting or coplanar overlaps. `tools/experiments/seam_probe.py` is used instead.
- **Unequal detail density.** Density varies 18× between modules (shutter vs plain wall).
- ~~No LODs.~~ Closed in Phase 21: the houses export LOD1/LOD2 (`lods: [0.5, 0.25]`, silhouette 0.945–0.996), and the kit shares one trim sheet.

## Reproduce

From the repository root (Python 3.11+, `pip install -r requirements.txt`):

```bash
# 1. validate + export every module and house (writes assets/<name>/export/)
for a in assets/house_*/; do ./sw export "$(basename "$a")"; done
for h in house_cottage house_townhouse house_workshop house_roof_section house_wall_window; do ./sw export "$h" --target godot; done
# 2. seam probe (0 visible same-facing pairs expected at 2 mm)
for h in house_cottage house_townhouse house_workshop; do python tools/experiments/seam_probe.py "$h" --tol 0.002; done
# 3. rebuild this folder (sources, materials, textures, GLBs, renders, reports, metrics.json)
python tools/experiments/build_mhp_bundle.py
```

**Stress test.** Edit `bay`, `storey`, `timber`, `post` or `pitch` in `packs/cozy_house.yaml`, then re-run steps 1–2. The recorded run used bay 2.4, storey 3.3, timber 0.22, post 0.32 and pitch 55. It rebuilt all three houses with no coordinate edits.
