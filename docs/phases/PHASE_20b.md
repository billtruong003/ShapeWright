# Phase 20b: cleanup of known defects (track A)

Branch `phase/20b-cleanup`. Plan: docs/REMAINING_WORK.md §3 (A1–A8).

**Verdict: PASS.** Every task shipped with a regression test (`tests/test_cleanup_20b.py`).
One gate was met in a different way than planned (A1, see below), and one item is not verified here (A7 runs only on Windows CI).

## What shipped

| task | change | class | why it is generic |
|---|---|---|---|
| A1 | 78 → 0 flagged seam pairs in 15 benchmark assets | VALIDATION GAP + asset fixes | see below |
| A2 | `tavern_chair.seat_height` min 0.40 → 0.42 (its own check is ≥ 0.42); the variants tutorial uses 0.42 | BUG (asset) | — |
| A3 | `sw export NAME --preview` → `export/NAME_preview.glb` without collision proxies or LOD files; the docs gallery uses it, `_strip_collision` is deleted | ERGONOMICS | every web viewer draws every mesh |
| A4 | `house_door` brace ranked 8 mm shallower than the ledges (12 mm at first; that made it 26 mm thick, under the style's 30 mm minimum, found in Phase 19b) (`seam_probe house_townhouse --tol 0.002`: 0 pairs) | BUG (kit) | depth-rank rule of MODULAR_HOUSE_PACK_01 |
| A5 | build products of library examples go to `<project>/.build/library/<name>/` (`paths.out_dir`); `sw materials` builds from memory instead of writing a temp file next to the source | BUG | a pip install puts the library in site-packages |
| A6 | `(2 info items hidden: UV_UNLOCKED, ASM_CONTACT_ONLY; --verbose to show)` | ERGONOMICS (FA-11) | — |
| A7 | `sw.cmd` launcher for Windows clones; `.gitattributes` keeps it CRLF; CI runs `sw.cmd doctor` on Windows | ERGONOMICS | — |
| A8 | source issues carry `src` = file:line of their `where` (variant first, then its base); text shows `[t/asset.yaml:11 parts.b.positon]` | ERGONOMICS (HARDENING, open since v0.1) | every source error |

Also: CI now runs on pushes to `phase/**` and `release/**` branches (it ran only on `main` and PRs), and
`tests/update_golden.py --changed a,b` exists (see "Golden").

### A1 in detail

The 78 pairs were of two kinds.

1. **Faces on the ground (36 pairs, 6 assets).** The bottom faces of a stringer and a newel post, of a stand post and its
   foot, of a wall and its plinths, all lie on y = 0 and face down. The floor covers them, so they can never z-fight.
   The seam validator now treats a downward face on the ground plane as hidden (VALIDATION GAP: false positives; the
   rule holds for any grounded asset). This replaces the planned fixes for wooden_staircase (+3 variants), pipe_assembly
   and stone_doorway: their geometry is unchanged.
2. **Real coincident faces (42 pairs, 9 assets)**, fixed in the sources with the three recipes:

| asset | pair | fix |
|---|---|---|
| ornate_fountain | bowl2 segments (overlap strip along each joint) | the wedge apex sits 0.5 mm short of the axis instead of 1 mm past it (at the axis exactly the boolean leaves degenerate faces) |
| park_bench (+unreal) | rear leg / seat rail / back post side faces | rail 12 mm and post 3 mm thinner across the frame |
| roof_section | rafter plumb cuts on the wall plate faces | plates 4 mm inboard (the "2 m eave to eave" check holds) |
| mine_cart | axle ends on the hub faces | axle ends 3 mm proud |
| storage_chest (+unreal) | hinge pin ends on the knuckle ends | pin ends 3 mm past |
| tavern_table | stretcher / cross stretcher bottoms | cross stretcher 3 mm slimmer |
| well_winch | crank end on the grip end | grip runs 4 mm past the crank |
| house_door (kit) | brace / ledges (A4) | depth rank |

The seam report also says **where** now: `near (0.63, 0.41, -0.2), facing +x`, and `data.at` / `data.normal`. Finding
the 42 real pairs took one script run with this; without it each pair needed a render per part.

Evidence (before | after, textured): `phase20b/evidence/{park_bench,roof_section,ornate_fountain,mine_cart}_before_after.png`.
They look the same at a glance, as the gate asks.

## Golden

14 assets changed geometry on purpose: house_cottage, house_door, house_townhouse, house_wall_door, house_workshop (the
door brace), mine_cart, ornate_fountain, park_bench, park_bench_unreal, roof_section, storage_chest, storage_chest_unreal,
tavern_table, well_winch. Their Windows hashes are dropped (Windows CI compares the signature until its hash is merged
back from the CI artifact).

Found on the way: golden.json had been recorded on Windows only, so Linux compared signatures. `update_golden.py` then
classified 4 of the changed assets as "same geometry, add this platform's hash", because a 3–6 mm edit inside the bounds
does not move the signature, which would have left stale Windows hashes. Fixed with `--changed`, and the Linux hashes of
the other 57 unchanged assets are now recorded.

## Gate

| gate | result |
|---|---|
| seam check: 0 flagged benchmark assets | **met** (`test_benchmark_assets_are_seam_clean`) |
| sheets look the same at a glance, before/after for 3 assets | **met** (4 pairs) |
| goldens updated and explained | **met** |
| `sw validate tavern_chair --set seat_height=0.42` passes | **met** |
| gallery renders the real models; Khronos 0 errors on preview files | **met with exceptions**: preview export runs the same Khronos check (0 errors on barrel and storage_chest); the gallery is rebuilt by the docs workflow |
| townhouse door probe 0 pairs | **met** |
| review/render/export of `barrel` with the library read-only | **met with exceptions**: tested with a separate project (the library folder is unchanged after review + export); a real read-only folder cannot be simulated as root in this container |
| `sw.cmd doctor` exits 0 on Windows CI | **not verified here**: runs in the Windows CI job |
| a typo on a known line reports that line | **met** (also inside a variant) |

## Not done

- `export: {preview: true}` in the source (the plan mentioned it): the CLI flag covers every caller found (site, workbench).
