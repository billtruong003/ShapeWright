# FRESH_AGENT_08: engine-ready delivery for Godot and Unreal (Phase 12 gate)

- **Date:** 2026-09-29 · **Repository state:** commit `1d0e27d` (Phase 12 implementation)
- **Plan:** [FRESH_AGENT_08_PLAN.md](FRESH_AGENT_08_PLAN.md) · predictions E1–E6 in [../PRODUCTION.md](../PRODUCTION.md)
- **Artifacts:** `assets/{storage_chest,park_bench,torch_bracket}` (godot profile) and `*_unreal` (extends variants)

## Observed (verified)

| Metric | Value |
|---|---|
| Wall clock / tool calls / tokens | ~17 min (1,033 s) / 68 / ~181k |
| Framework modifications | **0** |
| Exports | 6/6 validated, 0 errors or warnings; Khronos-clean; Unreal versions with `_LOD1.glb` (silhouette 0.93–0.96) |

**In-engine verification (Godot 4.3's importer; the agent could not run Godot).** I ran it
afterwards on all three Godot exports:

| Asset | Meshes / surfaces (draw calls) | Physics | Other |
|---|---|---|---|
| storage_chest | 2 / 4 (static + `lid` node on the hinge axis) | 1 convex body | textured; socket `SOCKET_loot`; grounded |
| park_bench | 1 / 2 | 12 convex bodies | 3 sitting sockets; grounded |
| torch_bracket | 1 / 3 | 1 convex body | `SOCKET_flame`; wall-mounted |

No visible collision meshes and no import errors. The agent's own lid-swing test found that its first
hinge pivot cut into the straps while opening. It moved the pivot onto the hinge axis and recommended
a 0–90° hinge limit.

## Predictions vs outcome

| # | Prediction | Outcome |
|---|---|---|
| E1 | finds `export.target` via profiles/docs | ✔ read PRODUCTION.md and the profiles |
| E2 | Godot: convex bodies, no visible proxies | ✔ (verified in Godot) |
| E3 | draw calls ≤ materials + moving parts | ✔ 4 / 2 / 3 |
| E4 | a moving part keeps its node and pivot | ✔ `lid` at (0, 0.42, −0.262), then checked by the agent's swing simulation |
| E5 | LODs for Unreal; silhouettes not checked unless surfaced | ✔ files written; the agent **did** read the reported silhouette values |
| E6 | 0 framework changes | ✔ |

## Findings and action

| Finding | Class | Action |
|---|---|---|
| Collision always went on the root: a hinged lid could not have collision that moves with it | **ABSTRACTION** (collision vs rigid groups) | proxies belong to rigid groups. Single modes give one proxy per group; Godot proxies are children of their group's node. **Verified in Godot:** the lid's `StaticBody3D` is parented to the lid node |
| `UCX_<asset>_NN` did not match the mesh name `<asset>_static` (Unreal pairs UCX shapes with a mesh by name) | BUG (Unreal convention) | named after the mesh: `UCX_<asset>_static_00`, `UCX_lid_00` (convention; untested in Unreal) |
| No way to export one asset to two engines (the agent made a variant per engine) | ERGONOMICS | `sw export ASSET --target unreal` writes `export/ASSET_unreal.glb` (+ LODs); targets carry default LODs |
| The PBR hint's own example colour (#4c5057) failed the check | BUG (hint) | the check is on the mean texel colour, which texture variation lowers; example #5a5f66, with the reason stated |
| `strut` section axes swap for legs leaning in different planes | ERGONOMICS | `depth_axis: x | y | z` |
| No in-engine check without Godot | environment | documented: `tools/engine/godot_check.py` with `SW_GODOT` |
| Unreal-side behaviour (glTF import of UCX, LOD assignment) unverified | **honest limit** | recorded; no Unreal in the container |

## Phase 12 gate

"A generated asset should be capable of entering a normal game-engine pipeline without significant
manual cleanup."

| Criterion | Verdict | Evidence |
|---|---|---|
| Godot pipeline | **PASS** | three agent-made props imported by Godot's own importer: physics, draw calls, pivots, sockets, textures and scale correct, no cleanup |
| Unreal / Unity pipeline | **PASS by convention only** | UCX naming, LOD files and merge follow the documented conventions; not tested in those engines |
| engine logic outside the core | **PASS** | `export/targets.py` + profiles; the geometry model is unchanged |
| no framework changes by the agent | **PASS** | 0 |

**Caveat:** only one engine was tested. The Unreal and Unity claims are limited to documented conventions.
