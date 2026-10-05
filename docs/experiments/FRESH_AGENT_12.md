# FRESH_AGENT_12: release acceptance (1.0.0)

A fresh agent with **only** `llms.txt` and the 1.0.0 wheel installed in a clean venv (`pip install
shapewright-1.0.0-py3-none-any.whl`), in a new project (`sw init`). It was not allowed to read the repository.
Two unseen requests:

1. *"A stylized wooden signpost with two arrow-shaped signs pointing in different directions, for a cozy mobile
   game, under 800 triangles, exported for Godot."*
2. A 3-module fence kit on a shared pack (`fence_post`, `fence_panel`, `fence_gate`) and a `fence_run` that places
   them with `asset:` instances on pack-param arithmetic, seam-clean, exported.

**Verdict: PASS.** Both deliverables export PASS. The agent rated the tool 7/10 from `llms.txt` alone and listed
13 friction points; the 8 that are framework problems are fixed in the release (below).

## Results

| task | final status | triangles | reviews | sheets opened |
|---|---|---|---|---|
| signpost | `PASS signpost tris 166/800 ... materials 2`, all layers PASS incl. export (Godot target) | 166 | 4 (the first did not build) | 3 of 3 |
| fence kit | `PASS fence_run tris 1368/1500 parts 38 ... materials 2`, `seam_zfight_pairs: 0` | 50 + 340 + 488 per module | 3 run + 1 gate + 1 pack sheet | 3 of 5 (fixed two WARNs without opening the sheet: recorded as a lapse) |

Sheets and sources: `fa12/signpost_sheet.png`, `fa12/fence_run_sheet.png`, `fa12/fence_pack.png`, `fa12/sources/`.
Each sheet changed something: the signpost's boards were spindly and nearly collinear (chunkier, V yaw), then one
arrow was foreshortened from the 3/4 camera (yaw −8/32, longer boards); the gate read like a panel (gate pickets
dropped 14 cm, taller stiles).

## Friction and what the release did about it

| # | finding | fixed in 1.0.0 |
|---|---|---|
| 1 | `sw pack --pack fence_kit` crashed with a traceback (installed copies) | **BUG**: `pack.select` shadowed the `paths` module with a local list; it also only looked in one folder. Now project + library members (`test_pack_by_name_finds_members...`) |
| 2 | `sw doc CODE` said "see docs/VALIDATION.md", which installed copies do not have | the wheel ships `_lib/docs/VALIDATION.md` and `ASSET_FORMAT.md`; `sw doc CODE` prints the code's row (severity, meaning, fix) |
| 3 | `sw doc pivot` → unknown name | `sw doc KEY` explains part, instance and top-level keys |
| 4 | the brief proposed `profile: godot` (5000 tris) for "mobile ... for Godot" | the platform sets the profile, the engine becomes the export target (`--target godot`) |
| 5 | the pack format and `asset.placement` were not in llms.txt | both added; also "mobile, for Godot = profile + target" and "chamfer on extrude needs a convex outline" |
| 6 | "thinnest dimension 3.0 cm < style minimum 3.0 cm" | two decimals (2.96 cm) |
| 7 | `OP_FACES_INVERTED` advised lowering an amount that was already small; a new seed fixed it | the hint names the seed |
| 9 | a snapshot of a source that does not build printed FAIL without saying nothing was recorded | it says so, exit 2 |
| 10 | `sw new` printed a path where the rest uses the name | prints the name for project assets |
| 13 | llms.txt said export always runs the Khronos validator | it says when (Node + tools/gltf-validator); the Docker image has it |

Not changed, recorded: rotating about an arbitrary point (#8: `rotate_about` takes center or anchor; the agent
wrote `c * cos(a)` by hand) is a backlog item; the seams result is only in `--json` metrics when clean (#11).
