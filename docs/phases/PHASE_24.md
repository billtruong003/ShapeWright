# Phase 24: native rigging and clips (track G, G4 and G5)

Branch `phase/22-organic` (stacked). Plan: docs/REMAINING_WORK.md §9 (G4, G5).

**Verdict: PASS.** The chibi fox is a rigged game character: 19 joints fitted from its own coordinates, bone-heat
weights, three procedural clips, and a skinned GLB that the Khronos validator passes with 0 errors and 0 warnings.
Godot 4.3 imports it headless with the skeleton intact and the clips playable. No standard pose or clip frame
loses more than 10 % of the volume (no candy-wrapper collapse). Rigid clips (a lid, a wheel) work without a skeleton.

## What shipped

| piece | where | notes |
|---|---|---|
| `rig:` block, templates `biped`, `quadruped` | `rig.py` | joints given or fitted from the bounds; `_l` mirrored to `_r`; extra chains (a tail) name their parent |
| bone-heat weights | `backend.bone_heat` | `(L + M H) w = M H p` with a cotangent Laplacian (clamped), one sparse factorisation for all joints; top 4, normalised; unreached vertices bound to their nearest bone |
| poses, linear blend skinning | `rig.posed`, `rig.posed_view` | rest frames axis-aligned; the posed view keeps the rest UVs and textures |
| glTF skin | `export/gltf.py` | joint nodes, inverse bind matrices, `JOINTS_0` / `WEIGHTS_0`; skinned meshes are scene roots; rigged assets export unmerged |
| procedural clips idle, walk, wave (G5) | `rig.clip_pose`, `rig.clip_keys` | rotation channels (plus root translation) at 16 keys; loops; parameters per clip |
| rigid clips | `animations:` | rotation about a part's pivot (its hinge group's node when merged): once, pingpong, cycle (≤ 60° between keys) |
| validators | `checks.rig_weights` | `RIG_INVALID`, `RIG_BONE_UNUSED`, `RIG_UNWEIGHTED`, `RIG_ASYMMETRIC` (area-weighted), `RIG_POSE_COLLAPSE`, `ANIM_INVALID` |
| renders | `sw render NAME --poses`, `--clip walk` | the pose sheet; a looping GIF |
| Godot check | `tools/engine/godot_check.py` | reports bones, skinned meshes, AnimationPlayer clips |

Found on the way:
- **Left/right comparison.** Comparing left/right weights by vertex count flagged a false asymmetry, because decimation leaves different vertex counts on the two sides. The weights are now compared by area.
- **Exporter name clash.** The animation sampler list reused the name of the exporter's texture sampler list. The first export lost its texture samplers, and Khronos reported it at once.

## Gates

| gate | target | measured | met |
|---|---|---|---|
| rigged fox in Godot headless | skeleton intact | 19 bones (the same names as the rig), 1 skinned mesh, 0 import errors (`test_godot_imports_the_rigged_fox_and_its_clips`) | yes |
| pose sheet without candy-wrapper | — | volume kept: A 0.97, walk 0.99, sit 0.96, wave 0.99 (≥ 0.9 tested for every pose and every third clip key) | yes |
| Khronos | 0 errors | 0 errors, 0 warnings (fox, chest) | yes |
| clips play in Godot (G5) | — | AnimationPlayer: idle 2.0 s, walk 1.0 s, wave 1.2 s; the chest's `open_lid` 1.6 s | yes |
| a turntable / pose GIF in the record (G5) | — | `phase24/evidence/fox_walk.gif`, `fox_wave.gif`, `fox_poses.png` | yes |
| rigid clips (G4) | doors, lids, wheels | `storage_chest` opens its lid (pingpong) | yes |

Tests: `tests/test_rig.py` (17), plus the Godot engine test in `tests/test_production.py` (CI's `godot` job).

## Limits, said plainly

- **Linear blend skinning:** a raised arm stretches the chibi torso on that side (the wave pose). Dual-quaternion skinning or a shoulder joint would help. It is not volume loss, which the gates measure.
- **Tested animals:** the quadruped template is built and its walk is defined, but no quadruped asset exists yet. Only the biped is tested on a real character.
- **No retargeting:** clips are generated per skeleton; a clip made for one character is not transferred to another.
- **Unity and Unreal:** skinned import is by convention (standard glTF skins) and not tested in those engines.
