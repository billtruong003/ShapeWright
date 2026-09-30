# Tight budgets: VR, mobile, web

Profiles set per-prop budgets. `budget:` in an asset overrides them:

| profile | triangles | materials | texture |
|---|---|---|---|
| `vr_standalone` | 1,200 | 1 | 512 |
| `mobile_low` | 600 | 1 | 256 |
| `mobile_mid` | 1,500 | 2 | 512 |
| `web` | 2,000 | 2 | 512 |
| `desktop_indie`, `godot`, `unity`, `unreal` | 5,000 | 3 | 1,024 |

For a Quest-class version of the library's desktop lantern, start with a variant:

```bash
# run
sw new vr_lantern --from iron_lantern
sw doc vr_standalone
```

Give the variant the VR profile and its budget:

```yaml
# append: assets/vr_lantern/asset.yaml
profile: vr_standalone
budget: {triangles: 1200, materials: 1}
```

```bash
# run
sw validate vr_lantern          # expect-fail: 4 materials > budget 1
sw stats vr_lantern             # triangles and material per part: what to merge or simplify
```

The budget layer reports `BUDGET_MATERIALS` with the material names, and the heaviest parts when triangles run over. Fix them in this order: merge materials (one atlas), fewer segments, fewer parts, then `decimate`. Export with `merge: by_material` (one draw call per material) and `lods: [0.5, 0.25]` when the engine needs LOD files.
