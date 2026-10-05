# Phase 19b: finish the kit (track B)

Branch `phase/19b-houses`, stacked on `phase/20b-cleanup`. Plan: docs/REMAINING_WORK.md §4 (B1–B6).

**Verdict: PASS.** This also closes Phase 19's PARTIAL: all three demo houses are now built only from module-asset instances.

## What shipped

| task | result |
|---|---|
| B1 townhouse from modules | 309 → **66** non-comment lines; 33,422 triangles before and after (identical count), same bounds, same look (`phase19b/evidence/house_townhouse_before_after.png`) |
| B2 workshop from modules | 437 → **95** lines; 45,668 triangles before and after, same bounds and look (`house_workshop_before_after.png`). The shared grid line is placed once (main-block posts, walls, footing); the wing roof still dies into the main wall |
| B3 stress test | bay 2.4, storey 3.3, timber 0.22, post 0.32, pitch 55 in a temp copy: 0 coordinate edits, 0 seam pairs, all three houses validate (texture-density warnings only) (`stress_bay2.4_storey3.3_pitch55.png`) |
| B4 bundle | `modular_house_pack/` rebuilt: 29 module/house GLBs + Godot variants, Khronos 0 errors, metrics now count module-asset reuse and house source lines |
| B5 sockets through `asset:` | an instance brings the instanced asset's sockets as `<instance>_<socket>`; they follow rotate, array and mirror (mirror reflects the rotation); the host's own socket wins a name clash |
| B6 window-size family | pack `win_w_small`, `win_h_small`, `win_h_tall`; `house_wall_window size: 0 small / 1 standard / 2 tall`, one head line; shutters are measured, so they follow. Small windows on the townhouse side walls, tall windows on the tavern front (`window_sizes.png`) |

Module params added so the houses could be pure instances, each defaulting to the old value (module goldens unchanged):
`house_wall_upper.seed`, `house_beam.depth` / `seed`, `house_wall_door.leaf` (0 = a bare opening, for the inner wall
between the tavern and the workshop).

## Framework changes

| change | class | why generic |
|---|---|---|
| B5: sockets of instanced assets (`World.sockets`, `_Group` carries socket frames through array/mirror, `frame_to_euler`) | CAPABILITY GAP | any asset that places another asset with a socket (a lamp's hook, a chest's loot point) lost it |
| xatlas atlases are destroyed a few unwraps later (`backend._retire`) | BUG | `sw validate` hung forever twice in this run: `xatlas::Destroy` → `std::thread::join` at 0 % CPU (py-spy). The TaskScheduler destructor loses the wake-up of a worker that has just finished; delaying the destroy lets every worker reach its wait. No measurable cost (400 × 41 unwraps: 34.5 s before, 7.6 s per 100 after) |

Two unplanned framework changes: under the stop limit of 3.

Also fixed: the Phase 20b door brace was 26 mm thick, under the style's 30 mm minimum (`STYLE_THIN_FEATURE` on the
townhouse); it is 30 mm now with an 8 mm depth rank to the ledges.

## Gate

| gate | result |
|---|---|
| townhouse ≤ 150 lines, workshop ≤ 220 lines | **met** (66, 95) |
| same triangle count ±2 % | **met**: identical before the window sizes; after B6 the townhouse has +176 (+0.5 %) for the small-window braces |
| 0 seam pairs (`seam_probe --tol 0.002`) | **met** on all three houses, also in the stress copy |
| `sw validate` PASS or WARN (texel only) | **met**: PASS on both |
| before/after renders | **met** |
| stress test: 0 coordinate edits, 0 seam pairs | **met** |
| B6: all three sizes validate, seam-clean, shutters measured | **met** |

## Golden

Changed on purpose (`update_golden.py --changed`): house_townhouse,
house_workshop (seeds of the band beams now come from the module instances; windows B6), house_door, house_wall_door,
house_cottage (the door brace, 30 mm). The modules that gained params (house_beam, house_wall_upper, house_wall_window) are unchanged.
