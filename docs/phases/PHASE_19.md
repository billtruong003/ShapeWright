# Phase 19: composition

**Verdict: PARTIAL.** Every composition capability shipped and was proven on the kit:
- the cottage is now built from module assets;
- its source is 76 % shorter;
- hand-derived offsets are 0 across all three houses;
- the stress test passes.

The townhouse and workshop were only partly converted (their shopfronts), so the "house sources ≥ 50 % shorter" gate holds for one house of three.

Branch `phase/19-composition`, stacked on `phase/17-mcp`. It is not merged.

## What shipped

| change | class | why it is generic (evidence) |
|---|---|---|
| **Nested components**: a component part may be a component instance (4 levels deep, `SRC_CYCLE` on self-inclusion). Names and material maps compose outward. | ABSTRACTION GAP | MHP-01 §5: houses could not reuse a *wall with a window* as a unit, so every house repeated 3–4 component instances per bay. |
| **Asset instances**: `asset: NAME` places a whole other asset. `with:` sets its own params (pack params are read-only: `PACK_OVERRIDE`). Materials merge; a differing definition is `MATERIAL_CONFLICT` unless mapped. Guarded against cycles and depth. | ABSTRACTION GAP | MHP-01 §5: "a house cannot place a module asset". Module and house sources duplicated each other, and one change had to be mirrored in 2–5 places. |
| **`measure:` on instances**: queries run against everything built before the instance; results feed `with`, `position`, `rotate` and `enabled`. | ABSTRACTION GAP | MHP-01 §13: shutter and awning depths were hand-derived (`wall_t/2 + 0.024`, `wall_t/2 − 0.027`) and had to be repaired twice. |
| **`pivot:` on instances**: the group becomes one hinged node (its first root part carries the pivot; the other parts become its children). | CAPABILITY GAP | MHP-01 §16: door swing pivots could not be authored. |
| Prefix-aware reference renaming inside components (`slat_2`, `left_post`) | BUG | A component part referencing a sibling's array instance was never renamed. |
| `World.groups`: group names resolve to all their parts, nested ones included, for `measure` | — | Needed for `gap` / `section` / `ray` on a nested instance. |
| `sw doc component`, `sw doc asset`; ASSET_FORMAT "Composition"; llms.txt | — | Docs. |

**Kit changes that use it:**
- **Module params.** Modules gained their own public params, all with defaults equal to the old values, so their goldens are unchanged:
  - `house_wall_window.shutters/seed`, and `seed` on the plain, door and shopfront walls;
  - `house_roof_section.deep`, `house_roof_end.deep/left`, `house_gable.deep`;
  - `house_ridge.length`, `house_chimney.height/shoulder`.
- **Measured placement.** `house_wall_window`, `house_wall_window_offset` and `house_wall_shopfront` now place shutters and awnings with `measure:` on the window frame and the stud face. The new positions are within 2 mm of the old hand values (the difference is the real jitter). The seam probe finds 0 z-fight pairs in these modules.
- **Cottage.** `house_cottage` is rewritten as 22 module-asset instances. Source before: `phase19/evidence/cottage_before_phase19.yaml`.
- **Shopfronts.** `house_townhouse` and `house_workshop` shopfronts use the `house_wall_shopfront` module asset (with `seed`).

## Evidence

| measure | before | after |
|---|---|---|
| cottage source | 255 lines / 234 non-comment / 11,240 bytes | **74 / 56 / 5,152** (−76 % non-comment lines, −54 % bytes) |
| cottage geometry | 24,476 tris, 370 parts | 24,476 tris, 370 parts; same look (`phase19/evidence/cottage_from_module_assets.png`) |
| hand-derived offsets in the kit (`0.024` / `0.027`) | 8 sites | **0** |
| seam probe, 2 mm (cottage / townhouse / workshop) | 0 / 2* / 0 | 0 / 2* / 0 |
| stress pack (bay 2.4, storey 3.3, timber 0.22, post 0.32, pitch 55) | — | all three houses rebuild with no edits; WARN only (texel density, stale UV lock); cottage 0 z-fight pairs |

\* The 2 townhouse pairs are `door_brace ↔ door_ledge_0/1`, 2.4 cm² each. They already exist on the base branch, so Phase 19 did not cause them. The MHP-01 final probe JSON did not list them (see Phase 20).

**Tests.** `tests/test_composition.py` (5 tests):
- a nested table → frame → leg with composed names and materials, and an attach to a nested sub-part;
- the component self-cycle;
- asset instances with `with` overrides, arrays, and `measure` on an asset instance;
- unknown param, asset cycle, `MATERIAL_CONFLICT` and its explicit mapping;
- `measure` + `pivot` on a component instance.

All 414 tests pass. Goldens changed only for the assets listed above.

## Gate

| gate item | result |
|---|---|
| houses instance module assets | **met for the cottage**; townhouse and workshop only for shopfronts |
| house sources ≥ 50 % shorter | **met for the cottage (−76 %)**; not measured for the others (not converted) |
| hand-derived offsets drop to 0 | **met** (all three houses and all modules) |
| goldens unchanged or explained | **met** (see above) |

## Left for later

- Convert the townhouse and workshop fully. Upper-storey walls and the wing need module params (`height`, `braces`) in the same way, which is mechanical now.
- Sockets of an instanced asset are not imported.
- The `modular_house_pack/` bundle GLBs were not re-exported. They predate this phase, and their geometry is equivalent.
