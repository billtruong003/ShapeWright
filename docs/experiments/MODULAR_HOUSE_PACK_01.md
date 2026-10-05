# MODULAR_HOUSE_PACK_01: a modular house kit as a real-user acceptance test

**Verdict: PARTIAL.** The kit works:
- 26 modules and 3 visibly different houses, all built from one pack.
- 0 visible z-fighting pairs.
- A 5-parameter stress test rebuilt everything with no coordinate edits.
- Valid, game-ready GLBs.

It is not a strong PASS, for two reasons:
- **Gate 6:** normal kit work needed 3 framework changes.
- **Gate 9:** readability by a fresh agent was not tested.

Details are in §17.

## 1. Goal

Use Shapewright the way a real environment artist would: build a coherent, reusable stylized medieval / cozy-fantasy house kit. It uses timber frame, plaster, stone and shingles, and has at least 24 modules. Then assemble three different houses from it.

The test is whether the framework's reuse and spatial systems produce modules that connect predictably, survive parameter changes, have clean seams and export game-ready. This is an acceptance test, not a feature sprint. Framework changes were allowed only for reproducible, generic defects, each with a regression test. Everything else is recorded as a finding.

## 2. Branch / commit

- **Branch:** `test/modular-house-pack` in `billtruong003/shapewright`, cut from `main` at `1056ee1` (Phase 15).
- **Commits:**
  - `8f91e5d`: MHP-01, the pack, components, 26 modules and the cottage prototype.
  - `bad6353`: MHP-02/03, the three houses, the seam probe and its fixes, the stress test and the layout speed-up.
  - The final commit: the report, bundle and metrics.
- **Not merged.** The branch is left for manual review.

## 3. Dimensional system

The single source of truth is `packs/cozy_house.yaml`. It has 34 params and 7 materials, all read-only in every member asset.

| concept | rule |
|---|---|
| plan grid | `bay` = 2.0 m, half bay 1.0 m; walls run along grid lines, centred on them |
| nodes | a `post` (0.26 m square) stands on every grid node, so a corner is just a post |
| wall span | a wall module fills the gap between posts (`bay − post` = 1.74 m), so walls never overlap each other |
| levels | deck top of storey k = `base_h + k·storey` (0.5 / 3.5 / 6.5 m) |
| embedding | walls and posts start `sink` = 2 cm below a deck top; footings stop 2 cm below it. Nothing meets a deck face exactly, so there is no gap and no coplanar face |
| wall height | `panel_h = storey − floor_t + sink`, ending under the next deck; outside, a band beam (`band_h = floor_t − sink`) fills the floor zone between posts |
| sections | `timber` 0.18 (rails, plates, braces), `post` 0.26, `wall_t` 0.26 (the frame is flush on both faces), `plaster_t` 0.16 (set back 5 cm each side) |
| openings | standard `win_w×win_h` 0.8×1.0 @ sill 0.95; door 1.0×2.05; shopfront 1.36×1.45 @ 0.6 |
| roof | `pitch` 45°, `eave` 0.45, `verge` 0.3, shingle `course` 0.3, `tile_w = bay/6` (whole tiles per bay, so the bond is continuous across modules) |
| depth ranks | crossing timbers sit on 12 mm depth ranks per face (plates flush, studs −12 mm, braces −24 mm), so no two timbers are coplanar where they cross |

Every module is placed by its own origin using grid arithmetic only (`x = i·bay`, `y = level(k) − sink`). The origins are listed in `modular_house_pack/README.md`.

## 4. Module inventory (26 modules + 3 houses)

| group | modules | tris |
|---|---|---|
| walls (7) | plain (X-brace), window, window_offset, door, shopfront (+awning), half (half bay), upper (upper-storey window) | 188–1,012 |
| corners / framing (5) | corner (post+footing), post, beam_vertical, beam (band), brace | 44–150 |
| floors / foundation (4) | floor (1 cell), floor_half, footing, steps | 88–396 |
| roof (6) | roof_section (1 bay of slope), roof_end (verge), gable (infill + truss), ridge, roof_eave, chimney | 116–1,384 |
| openings (4) | window, door_frame, door, shutter | 132–432 |

Contact sheets are in `modular_house_pack/renders/modules_*.png`.

## 5. Reuse architecture

There are 12 kit components (`components/house_*.yaml`). They reuse one existing component (`plank_top`, from the blacksmith pack) and nothing else.

| component | instance lines | assets using it |
|---|---|---|
| `house_wall` (sill/head plates, studs, rails, braces, plaster infill with opening cuts, depth ranks) | 32 | 10 |
| `house_roof` (profile-extruded deck, wedge shingle rows even/odd with running bond, fascia, rafter tails, `align` + trim) | 28 | 7 |
| `house_timber` (one chamfered, jittered timber of any length/orientation) | 27 | 8 |
| `house_window_frame` | 17 | 8 |
| `house_footing` | 14 | 5 |
| `house_floor` (planks across joists) | 7 | 5 |
| `house_door`, `house_door_frame` | 6 each | 5 |
| `house_gable`, `house_ridge`, `house_steps` | 5 each | 4 |
| `house_chimney`, `plank_top` | 4 each | 4 |

- **Reuse mechanisms:**
  - Structural variation is expressed through public component params, for example `house_wall` with `opening: window|door|shop|none`, `offset`, `braces`, `glazed` and `height`.
  - Arrays (`each`/`skip`, nested) lay out posts, footings, shingle rows and roof bays.
  - `enabled` expressions switch optional sub-parts.
- **Duplication:** 0 exact duplicate inline parts across assets, and 0 structural duplicates (the same shape and ops in 3 or more assets).
- **Family vs variant vs pack:**
  - The pack holds conventions.
  - Components hold construction.
  - Modules are thin assets, 1 to 3 component instances each.
  - Houses are compositions of component instances.
- **Not used: anchors, sockets, `measure`, `attach`.**
  - Every relation in the kit is a shared dimension from the pack, so grid arithmetic was always enough.
  - `measure` was needed only once, to place shutters and awnings against another instance. The framework cannot do that (instances cannot measure other instances). That is a recorded limitation (§13, §16), not an escape.

**The main structural gap:** a house cannot place a module asset. Components cannot nest, and assets cannot be instanced inside assets. So the houses instantiate the same components the modules do, with the same params, instead of instancing `house_wall_window` itself.

This works, since the geometry is identical and so is the grid rule. But the house sources are verbose, at 180–480 lines each:
- the cottage has 28 instances and 18 arrays;
- the workshop has 57 instances and 33 arrays.

A per-module change must also be mirrored in the houses' params. That happened twice: the shopfront `glazed` param and the awning offset.

## 6. Shared materials

Seven materials are defined once in the pack:

| material | archetype | colour |
|---|---|---|
| `timber` | wood | #5a3a24 |
| `planks` | wood | #9a6a40 |
| `plaster` | painted | #e6d6b4 |
| `stone` | stone | #8c857a |
| `roof` | stone | #8e4a33 |
| `glass` | flat | — |
| `iron` | metal | — |

- **Drift:** no asset defines its own material. Pack materials are read-only in members (`PACK_OVERRIDE`), so drift is 0 by construction.
- **Grain:** timber grain follows each timber's long axis, because the UVs are per part and axis-aligned. The same timber reads as one family across modules (`materials/material_sheet.png` and the textured hero renders).
- **Atlases are baked per asset:**
  - base colour + ORM, 1024² for modules and larger for houses;
  - module texel density 111–747 px/m;
  - house texel density 34–50 px/m (a house is one atlas).
- **Limitation:**
  - There is no shared trim sheet or tiling texture across assets.
  - The textures are consistent, not shared, so a game pays texture memory per module.
  - House atlases at 34–50 px/m look soft up close. They are fine at third-person distance.

## 7. Parameterization metrics

The metrics come from `tools/experiments/mhp_metrics.py`. It uses the FA-02 methodology: `analyze_source.py` and `analyze_pack.py`.

| scope | literal | derived | measured | Parameterization Ratio | Abstraction Escape Rate (literal-shaped or mesh parts) |
|---|---|---|---|---|---|
| 26 modules | 39 | 203 | 0 | **0.839** | **0.000** (36 of 36 parts are component instances) |
| 3 houses | 139 | 1,123 | 0 | **0.890** | **0.000** (124 of 124 parts are component instances) |
| 12 components | 60 | 314 | 0 | 0.840 | 0.566 of component parts carry ≥ 1 literal |

**Per house:**

| house | Parameterization Ratio | literals | derived |
|---|---|---|---|
| cottage | 0.888 | 31 | 245 |
| townhouse | 0.876 | 51 | 359 |
| workshop | 0.901 | 57 | 519 |

**What the literals are:**
- *Component literals* are cosmetic constants: bevel sizes, jitter seeds, shingle overhang ratios, the door pull, nail and strap dimensions. They are not placement.
- *House and module literals* are mostly layout fractions, such as `1.5` (bay position of a door) and chimney offsets, plus two hand-derived surface offsets (§13).
- Mesh escapes: 0. Measure queries: 0. Attach: 0.

## 8. Runtime metrics

**Module triangles:** min 44, median 272, max 1,384 (the roof section, whose shingles carry the silhouette).

**Detail density:** 11–201 tris/m², an 18.6× spread. The shutter's plank battens are dense for their area; plain walls are sparse.

| house | tris | budget | parts → draw calls | materials | GLB | collision |
|---|---|---|---|---|---|---|
| cottage | 24,476 | 30,000 | 370 → 7 | 7 | 4.8 MB | single_box |
| townhouse | 33,042 | 45,000 | 571 → 7 | 7 | 5.9 MB | single_box |
| workshop | 45,080 | 60,000 | 725 → 7 | 7 | 6.6 MB | single_hull |

- **Merging:** `export: {merge: by_material}` merges hundreds of parts into one mesh per material. The authoring structure stays in the source; the GLB is flat.
- **Collision:** modules use `single_box`, except the roof section and roof end, which use `single_hull` so the slope is a real slope.
- **Validation:**
  - All 29 exports report PASS.
  - The Khronos glTF validator shows 0 errors, 0 warnings, 0 infos and 0 hints on every GLB.
  - The `_godot.glb` variants imported cleanly in Godot 4.3 headless (houses, roof section, window wall).

## 9. Visual iteration history

Each round used deterministic renders:
- contact sheets of all modules;
- textured and clay hero renders of the houses from three views;
- framed close-ups: `tools/experiments/closeup.py`.

Round 1 was the kit sheet plus the cottage prototype:
1. *"Shingle rows show magenta patches along the course edges."* The wedge polygon was 1 mm thin at its tail and the 6 mm wear jitter inverted it. Evidence: `renders/finding_shingle_jitter_inverted_wedge.png`. **Fix:** a real wedge profile, thick enough to survive the jitter.
2. *"Floor planks float above the joists."* The joists ran parallel to the planks, so only two touched. **Fix:** joists across the planks, and planks reach the tile edge so floors butt continuously.
3. *"Gable struts disappear into the infill."* With `depth_axis: x` the size order was swapped, burying the struts. **Fix:** size order corrected.
4. *"Door pull and barge boards hover 3–5 mm off their surfaces."* **Fix:** embedded 5 mm.
5. *"Roof tiles jump half a tile at every module seam."* Each section started its bond at its own edge. **Fix:** the pack param `tile_w = bay/6` plus an `align` param on `house_roof`, so the running bond is continuous across sections.

Round 2 was the seam close-ups: corner, window bay, gable apex, storey band, and the wing roof meeting the wall. The seam probe (§10) found 26 pairs, fixed as described there.

Round 3 was the three houses:
6. *"The shopfront reads as a glazed window, not an open counter."* **Fix:** a `glazed: 0` param on `house_wall`, mirrored into the townhouse and workshop.
7. **Design decisions checked on the renders:**
   - The townhouse puts its gable to the street and adds an awning and a tall chimney, so its silhouette is distinct from the cottage.
   - The workshop wing shares the main block's grid line, and the render and probe confirmed there are no doubled posts or walls there.

Round 4 was the stress renders (§15), and round 5 the final hero renders:
- The three houses clearly share one language: the frame rhythm, plaster, stone plinth and red shingles.
- Their silhouettes differ:
  - the cottage is low and wide, with a side chimney;
  - the townhouse is narrow and tall, gable to the street;
  - the workshop is an asymmetric L with a lower wing.

**Remaining critique, not fixed:** the windows are identical everywhere. There is no size variant; the kit has one standard window.

## 10. Seam findings

**What was checked:**
- the gaps and penetrations listed in the brief, by close-up renders;
- coplanar and same-plane overlaps, with `tools/experiments/seam_probe.py`:
  - it tests triangle pairs from different parts;
  - it clips them exactly in their common plane;
  - it tests whether a sample point just in front of the overlap is buried inside a third closed part (generalised winding number);
  - it runs a local plane-separation check.

**First cottage:** 26 visible same-facing pairs, all of which the standard validator passed. Evidence: `validation/seam_probe_cottage_iter1.txt`.

| case | area | cause | fix |
|---|---|---|---|
| head rail vs plaster infill | 616–664 cm² | the plaster opening cut ended exactly at the rail face | cuts extended by half a timber into the rail |
| X-brace a vs b | 402 cm² each (×4) | both diagonals on the same depth | 12 mm depth ranks per face |
| gable rake left vs right | 42 cm² | coincident at the apex | rank + embedding |
| barge board vs verge deck | 14 cm² | the barge face on the deck edge plane | barge embedded past the jitter |
| roof deck vs even shingle row | 1.9–11.3 cm² | the first course coincided with the deck face | deck and shingle faces separated by embedding beyond the jitter |
| stud and plaster ends; door brace vs ledge | small | same-plane ends | plaster span +1 cm into studs; brace ranked behind the ledge; wall jitter ×0.5 so jitter cannot undo a rank |

**Final result at a 2 mm tolerance:** 0 visible same-facing pairs in all three houses, and also under the stress pack.

| house | part pairs in contact | visible z-fight |
|---|---|---|
| cottage | 54 | 0 |
| townhouse | 71 | 0 |
| workshop | 96 | 0 |

The remaining pairs are back-to-back hidden contact: 9.8 / 9.4 / 14.0 m², a wall butting a post, a deck on a footing. Evidence: `validation/seam_probe_house_*_final.json`.

**Doubled walls and hidden geometry:**
- None on shared grid lines. The workshop wing places them once.
- Hidden internal geometry exists by design: the embedded ends of timbers (2–12 mm), and the deck underside inside the footing. That is a few hundred triangles per house.

**Gaps and floor heights:** none found in the close-ups. Floor heights are the same expression everywhere.

**UV seams and material discontinuities:**
- Each part has its own chart, so timbers show a texture discontinuity where two modules' timbers meet.
- It is hidden at every joint the kit has by post and plate overlaps. It would show on a long beam split across two modules.
- No plaster or shingle discontinuity is visible at module seams, thanks to the continuous tile bond.

**Merge-by-distance and welding:**
- These were not needed. Modules are separate closed parts, merged by material only.
- Coincident vertices between parts are never welded, and should not be, because the parts have different UVs.
- A merge-by-distance tool would not have fixed any of the 26 findings. They are coplanar overlaps of distinct surfaces, not near-duplicate vertices.

## 11. Validator blind spots (recorded, no validator added)

1. **Cross-part coplanar overlap / z-fighting.**
   - The standard pipeline passed all 26 pairs above, at 0.67–664 cm².
   - Example: `wall_back_0_head_rail` ↔ `wall_back_0_infill`, 664 cm², same facing. Validator: PASS. Expected: a warning.
   - As instructed, this is recorded with the experiment probe instead of adding a validator. Its real frequency in this kit was 26 pairs on the first honest attempt, so it matters.
2. **Contact vs embedding.** The validator's touch test accepts exact face contact. The shop awning touched the wall only by exact contact after the stress change. That is valid to the validator, but it is a hairline seam in a render. It was fixed by embedding.
3. **Jitter inverting thin geometry.** Wear jitter can invert a thin wedge (the magenta shingles) with no warning. The mesh is still closed, only inside out locally.
4. **Floating by a few millimetres.** Parts that were 3–5 mm off (door pull, barge boards) passed, because the floating tolerance is larger than a visible gap at close range.
5. **Near-parallel false positives (a probe finding).** The first probe version flagged planes 0.3 % apart. A local separation check fixed it, so the probe is trusted at 2 mm, not below that.

## 12. Framework changes (3)

| # | change | class | why it is generic, not asset-specific | test |
|---|---|---|---|---|
| 1 | Component instances accept `origin: keep`: the component's own origin is the pivot, not the bounding-box centre | ABSTRACTION GAP | Bounding-box placement moved roof pieces 2–10 cm whenever optional trim was enabled or disabled. Any kit piece with optional or asymmetric sub-parts cannot be placed by grid arithmetic without it. It rejects `origin: keep` together with anchor/attach. | `tests/test_components.py::test_component_origin_keep_places_the_components_own_origin` |
| 2 | A malformed `components/*.yaml` no longer crashes `sw caps` / `sw doc`; it reports "unreadable: YAML error at line N" | BUG | One unquoted `:` in any component doc string broke every documentation lookup in the repo | `tests/test_cli.py::test_a_broken_component_file_does_not_break_caps_or_doc` |
| 3 | UV charting runs each part at the resolution of its own atlas region instead of the full atlas resolution | CAPABILITY GAP (performance) | The 571-part townhouse took 95 s to lay out, and the CLI's 120 s limit killed `sw review`. Every many-part assembly hits it. After the change it takes 5 s, with no change to any golden. | existing surface and golden tests (UV state unchanged) |

Asset-driven additions: 0 new ops. The gate asks for 0 framework changes; this is 3. Changes #1 and #3 were needed for normal work: placing kit pieces, and reviewing a house.

## 13. Manual repairs

These are every place a coordinate had to be derived or fixed by hand, not by the grid rule:

1. **Shutter offset** `wall_t/2 + 0.024` (3 sites: `house_wall_window`, `house_wall_window_offset` and the cottage).
   - The shutter must sit on the stud face, which is 12 mm behind the plates.
   - An instance cannot measure another instance, so the depth is hand-derived from the rank rule.
   - It had to be re-derived after the stud re-rank of §10, when the shutters floated.
2. **Awning offset** `wall_t/2 − 0.027` (3 sites: `house_wall_shopfront`, the townhouse and the workshop).
   - Same cause. It was changed after the stud re-rank, and again when the stress test showed it touching by exact contact only (§11.2).
3. **Shingle `align`** per roof section, a derived expression from the bay index. It was written once, not repaired.

The stress test itself needed no coordinate edits.

## 14. Three-house results

| house | plan | storeys | distinguishing features | tris | status |
|---|---|---|---|---|---|
| `house_cottage` | 3×2 bays | 1 | eaves to the front, side chimney, shutters, steps, door centre | 24,476 | PASS |
| `house_townhouse` | 2×3 bays | 2 | gable to the street, shopfront with counter and awning, tall chimney, upper band | 33,042 | PASS |
| `house_workshop` | 3×2 main + 2×2 wing sharing a grid line | 2 + 1 | asymmetric L, wing roof dying into the main wall, offset windows, shopfront in the wing | 45,080 | PASS |

- No house needed a unique wall. Every wall is a standard kit wall configured by component params.
- The only special-case geometry is the wing roof's shortened sections, which use the `house_roof` trim param. Those are the same component.
- Hero renders: `modular_house_pack/renders/house_*_{front_right,back_left,front}.png`.

## 15. Stress test

The pack was changed after the kit worked, in a copy of the repo: `bay` 2.0 → 2.4, `storey` 3.0 → 3.3, `timber` 0.18 → 0.22, `post` 0.26 → 0.32, `pitch` 45 → 55. All modules and all three houses were rebuilt.

| check | result |
|---|---|
| attachments valid | yes: posts, walls and floors all derive from the same params |
| roof still connects | yes: the ridge, gables, verge ends and wing roof all follow the pitch |
| windows centred | yes: windows are placed as a fraction of the span |
| floors aligned | yes |
| UVs valid | yes: all exports report uv_overlap 0 |
| materials coherent | yes |
| seams | the seam probe found 0 visible pairs |
| validation | PASS/WARN (texel-density warnings only) |
| automatic re-flow | window walls gain side braces automatically once the span allows them |
| coordinate edits | 0 |
| repair found | 1: awning exact contact (§13.2), fixed at the source for both the default and the stress pack |

Evidence: `renders/stress_houses_textured.png` and `stress_houses_front_clay.png`.

## 16. Known limitations

- **No nesting.** Houses cannot instance module assets, and components cannot nest (§5). This causes verbose house sources and mirrored params. It is the biggest usability cost found.
- **No cross-instance measurement.** An instance cannot measure another instance. This caused the hand-derived shutter and awning offsets, and their re-repair.
- **No seam validator.** Seam checking lives in an experiment tool, not in the validator (§11).
- **No shared textures.** Atlases are per asset: no trim sheet, and soft texels on the houses at 34–50 px/m.
- **Uneven detail density.** Density spreads 18.6× between modules.
- **No LODs** were made for the houses.
- **Coarse collision.** House collision is one box or hull: no interior, no doorways.
- **No interiors.** There are no stairs or interior walls.
- **Pivot overrides.** A `pivot` cannot be set on a component instance, so door swing pivots are not authored. The door GLB's origin is its bottom centre, not its hinge.
- **One window size.** There is no window-size family in the kit.

## 17. Honest verdict: **PARTIAL**

| # | gate | result |
|---|---|---|
| 1 | three visibly different houses from one kit | **met** |
| 2 | predictable alignment without widespread hand offsets | **met with exceptions**: grid arithmetic everywhere, except 2 hand-derived surface offsets at 6 sites |
| 3 | meaningful structural reuse | **met**: 12 components, 158 instance lines, 0 duplicates |
| 4 | coherent shared materials | **met**: 7 pack materials, 0 drift (atlases per asset) |
| 5 | parameter changes do not destroy the kit | **met**: 5-param stress, 0 coordinate edits, 1 contact repair |
| 6 | no normal task requires framework modification | **not met**: 3 changes (1 bug, 1 abstraction gap, 1 performance), 2 of them needed for normal kit work |
| 7 | no z-fighting, duplicate surfaces or severe interpenetration | **met**: 0 visible pairs at 2 mm in all houses (after fixing 26 the validator missed) |
| 8 | game-ready GLBs export | **met**: 29 PASS, Khronos 0/0, Godot import OK |
| 9 | understandable and editable by a fresh agent | **not verified**: no fresh-agent run; house sources are long for the reason in §5 |
| 10 | visually intentional | **met in my review**: consistent frame language and distinct silhouettes; windows are repetitive |

**Why not PASS:**
- Gate 6 is failed outright.
- Gate 9 is untested.

**Why not FAIL:** the kit does what a modular kit must do.
- Pieces connect by one grid rule.
- It survives parameter changes.
- It produces three distinct, seam-clean, game-ready houses.

**What the test says about the framework:**
- Components, packs and read-only params are strong enough for a real kit.
- The missing pieces are composition and seam validation:
  - **composition:** nesting components or instancing assets, and measuring across instances;
  - **seam validation:** coplanar overlap between parts.
- Both are now backed by concrete recorded cases instead of speculation.

## 18. Addendum after Phases 19, 20, 20b and 19b

The limitations of §16 were taken up by the framework phases. State on 2026-10-05:

| §16 limitation | now |
|---|---|
| No nesting: houses cannot instance module assets | **closed** (Phase 19): all three houses are made only of module-asset instances: cottage 56, townhouse 66 (was 309), workshop 95 (was 437) non-comment lines; 97 instance lines over 16 modules (`metrics.json` → `module_asset_reuse`, `house_source_lines`) |
| No cross-instance measurement | **closed** (Phase 19): shutters and awnings are placed by `measure:` on the window frame and the stud face; no hand offsets remain |
| No seam validator | **closed** (Phase 20, 20b): `SEAM_COPLANAR_OVERLAP`, `OP_FACES_INVERTED`, `ASM_CONTACT_ONLY`; every benchmark asset and every house is seam-clean |
| One window size | **closed** (Phase 19b): `house_wall_window` `size` 0 small / 1 standard / 2 tall from pack params, one head line; small on the townhouse sides, tall on the tavern front |
| Instanced assets lose their sockets | **closed** (Phase 19b) |
| No shared textures, no LODs, coarse collision | open: Phase 21 (track F) |
| Uneven detail density, no interiors | open: backlog |

The 5-parameter stress test (§15: bay 2.4, storey 3.3, timber 0.22, post 0.32, pitch 55) was re-run on the
module-built houses: 0 coordinate edits, 0 seam pairs, every house validates (texel density warnings only, as the
houses grow); render in `docs/phases/phase19b/evidence/stress_bay2.4_storey3.3_pitch55.png`.

Gate 6 ("no normal task requires framework modification") would now be met for this kit: building the three houses
needed no framework change after Phase 19. Gate 9 (a fresh agent) is still not verified; it is part of release
acceptance (FRESH_AGENT_12, track E).
