# Validation

`sw validate ASSET` (or `sw review`, or `sw export`) runs every layer and prints
one summary line, per-layer status, design-check values and one line per issue:

```
FAIL tavern_table  tris 528/700  parts 12  size 1.406x0.760x0.798 m  materials 2  uv_overlap 0.0  texel 176.6 px/m
layers: source=PASS geometry=PASS assembly=FAIL budget=PASS intent=PASS surface=PASS style=PASS
checks: plank.max.y=0.76, plank.max.y - 0.46=0.3
  ERROR   ASM_FLOATING_PARTS [plank_1]: 1 part(s) do not touch the rest of the asset: plank_1  -> attach them to ...
```

`--json` prints the full structure, and it is always written to
`.build/report.json`:
`{asset, status, source_hash, counts, layers, metrics, issues:[{code, severity, layer, where, src, msg, hint, data}]}`. `src` is the file and line of a source issue (`my_asset/asset.yaml:42`; a variant's issue points into the variant, then its base); text output shows it as `[my_asset/asset.yaml:42 parts.leg.shape.size]`.
Exit code: 0 for PASS/WARN, 1 for FAIL, 2 if the source cannot be built.

## Deterministic vs perceptual

| Deterministic (validated here) | Perceptual (judged by the agent from renders) |
|---|---|
| closed, manifold, consistently wound meshes | recognizability, silhouette readability |
| parts physically connected; grounded; origin placement | proportions and visual balance |
| triangle and material budgets | style adherence, shape language |
| design-intent checks declared in the source | excessive or insufficient detail |
| UV bounds, overlap, texel-density spread | "does this belong in the same pack?" |
| glTF validity and round-trip | appeal |

The style layer is the bridge. It turns a few *measurable* aspects of a style
(minimum feature size for chunky styles, part and material counts) into
warnings. It never produces errors, because style is a judgement call.

## Layers and codes

### source (raised while building; the asset cannot be built)
| Code | Meaning | Typical fix |
|---|---|---|
| `SRC_PARSE` | YAML syntax error | fix indentation and quotes |
| `SRC_SCHEMA` | unknown key, wrong type, missing required field | follow the hint (did-you-mean) |
| `SRC_EXPR` | expression error or unknown name | check param spelling |
| `SRC_RANGE` | value outside an op's allowed range | respect `sw doc NAME` limits |
| `SRC_REF` | unknown part, material, profile, style or extends target | check names |
| `SRC_CYCLE` | circular params or attachments | break the cycle |
| `SRC_LIMIT` | resource limit exceeded (`limits.py`) | reduce segments, counts or subdivisions |
| `OP_FAILED` | a shape or op raised (for example a boolean on bad input) | check parameters and tool placement |
| `GEO_EMPTY` / `GEO_NONFINITE` | an op produced no or invalid geometry | revise the op |
| `ASM_MIRROR_ON_PLANE` | a mirrored part sits on the mirror plane | offset it or remove the mirror |
| `PARAM_OUT_OF_RANGE` (warning) | param outside its declared min/max | intended? widen the range |
| `MEASURE_FAILED` | a `measure` query has no answer (plane/ray misses, parts overlap for `gap`) | check the query against `sw stats` |
| `COMPONENT_PRIVATE` | `with:` sets a param the component does not expose | use a public param (listed in the hint) |
| `FAMILY_PRIVATE` | a variant overrides something outside the base's `interface` | ask the base to expose it (public param / `enabled:` switch) |
| `PACK_OVERRIDE` | an asset redefines a pack param/material or uses a different profile/style | use a new name, or change the pack for every member |
| `FAMILY_NO_INTERFACE` (info) | the base declares no interface; the variant depends on internals | add `interface:` to the base |

### geometry (per part)
| Code | Sev | Meaning |
|---|---|---|
| `GEO_OPEN_EDGES` | error (warning with tag `open_ok`) | boundary edges; the surface has holes |
| `GEO_NONMANIFOLD_EDGES` | error | an edge is shared by more than two faces |
| `GEO_WINDING_INCONSISTENT` | error | neighbouring faces disagree on orientation |
| `GEO_INVERTED` | error | closed surface with inward normals |
| `GEO_DEGENERATE_FACES` | error | zero-area triangles |
| `GEO_DUPLICATE_FACES` | error | the same triangle twice |
| `ANIM_INVALID` | error | an `animations:` entry names an unknown part, or is malformed |
| `RIG_INVALID` | error | the `rig:` block cannot be built (unknown template, a joint without a parent, two roots) |
| `RIG_BONE_UNUSED` | warning | a joint drives no vertex (its strongest weight is under 0.2): it sits outside the body |
| `RIG_UNWEIGHTED` | warning | vertices the bone heat did not reach (bound to their nearest bone) |
| `RIG_ASYMMETRIC` | warning | left and right joints' area-weighted influence differs by more than 25 % |
| `RIG_POSE_COLLAPSE` | warning | a standard pose (A, walk, sit, wave) keeps less than 85 % of the volume (candy-wrapper) |
| `GEO_BLEND_PINCHED` | warning | a `blend` shape's triangle budget cannot hold a gap narrower than its edges; the surface was pinched there (the message gives where) |
| `GEO_DUPLICATE_SURFACE` | warning | faces repeating another face's position with their own vertices (an unwelded copy, typical of imports): z-fighting, doubled triangles. Fix: `{type: clean, weld_distance: 0.0005}` |
| `GEO_PART_FRAGMENTED` | info | a part consists of several disconnected shells (expected for `combine`, `repeat`, multi-shell files) |
| `GEO_CUT_SPLIT` | warning | a subtract/intersect/boolean/flat_bottom cut split a piece into several (reported at the op) |
| `GEO_SLIVER_TRIS` | info | more than 25% very thin triangles (shading artefacts) |
| `OP_FACES_INVERTED` | warning | a displacing op (`jitter`, `noise`, `inflate`) turned faces inside out: the geometry is thinner than the displacement (the mesh stays closed, so the checks above pass; it renders as dark or missing patches). Reported at the op |

### assembly (semantic structure)
| Code | Sev | Meaning |
|---|---|---|
| `ASM_FLOATING_PARTS` | error | parts not connected to the grounded parts (contact tolerance 1 mm, exact Manifold distance); the message gives each part's gap to the nearest connected part |
| `ASM_FLOATING_TAGGED_NEAR` | warning | a part tagged `floating_ok` is within max(5 cm, 10% of the asset size) of a connected part: almost always a mounted piece placed a little off, not one meant to hover |
| `ASM_FLOATING_TAG_UNUSED` | info | `floating_ok` on a part that touches the asset: the tag does nothing now and would hide a later regression |
| `ASM_BELOW_GROUND` | warning | geometry below y = 0 |
| `ASM_NOT_GROUNDED` | warning | the lowest point is above y = 0 (for floor props) |
| `ASM_ORIGIN_OFFSET` | warning | origin outside the footprint of the grounded parts |
| `ASM_HIDDEN_PART` | warning | a part is (almost) entirely inside other parts: wasted triangles (see-through `alpha_mode` BLEND/MASK parts, e.g. lantern glass, do not count as hiding) |
| `ASM_SCALE_SUSPICIOUS` | warning | size suggests a units mistake (< 1 cm or > 200 m) |
| `ASM_CONTACT_ONLY` | info | parts touch their neighbours only face to face, with no overlap. Fine for parts that rest; mounted pieces should embed 1–5 mm past the jitter so no hairline shows after rounding or export |
| `SEAM_COPLANAR_OVERLAP` | warning | two parts share at least 0.5 cm² of the same surface, facing the same way, within 1 mm: it z-fights in an engine. Overlap buried inside a third closed part (generalised winding number), downward faces lying on the ground plane (y = 0, covered by the floor) and back-to-back contact are not reported. The message says where: a point of the shared surface and its facing. Data: `parts`, `area_m2`, `at`, `normal`. Fix: depth ranks (offset one face by a few mm), end one part inside the other, or cut one |
| `SEAM_SKIPPED` | info | the seam check is skipped above 400k triangles |

### budget (production profile)
| Code | Sev | Meaning |
|---|---|---|
| `BUDGET_TRIANGLES` | error | over the triangle budget; the hint lists the heaviest parts |
| `BUDGET_MATERIALS` | error | more material slots than the budget |
| `BUDGET_NEAR_LIMIT` | info | within 5% of the triangle budget |
| `MAT_UNASSIGNED` | warning | a part has no material |
| `MAT_UNUSED` | info | a declared material is not used |

### intent
| Code | Sev | Meaning |
|---|---|---|
| `CHECK_FAILED` | error (or the check's `severity`) | a `checks:` assertion is outside its range |
| `CHECK_ERROR` | error | the check expression cannot be evaluated |

### surface
| Code | Sev | Meaning |
|---|---|---|
| `UV_MISSING` | warning | no UVs (`uv.method: none` or xatlas unavailable) |
| `UV_OUT_OF_BOUNDS` | error | UVs outside 0..1 |
| `UV_OVERLAP` | error | more than 0.2% of used UV area covered twice (rasterized at up to 1024²) |
| `UV_TEXEL_DENSITY` | warning | texel density differs by more than 1.5x between parts (on a pack trim sheet: a face taller than its strip was scaled down) |
| `LIGHTMAP_UV_MISSING` | error | lightmaps are on (`uv.lightmap` or the profile) but a part has no `TEXCOORD_1` |
| `LIGHTMAP_UV_OVERLAP` | error | more than 0.2% of the used lightmap UV area is covered twice, or lightmap UVs leave 0..1 |
| `LIGHTMAP_UV_DENSITY` | warning | lightmap texel density differs by more than 2x between parts |
| `VERTEX_COLOR_MIXED` | warning | `archetype: vertex` materials next to textured ones: the asset still needs a texture |
| `NRM_FLIPPED` | error | vertex normals oppose their face |
| `UV_LOCK_STALE` | warning | `uv.lock.yaml` does not match the parts; regions recomputed (re-lock) |
| `UV_REGION_REGENERATED` | info | these parts changed since the lock; their charts were regenerated inside their fixed regions |
| `UV_UNLOCKED` | info | no lock; regions follow areas and may move (lock before texturing) |
| `ATTR_INVALIDATED` | info / warning | a topology-changing op dropped attributes (warning if an imported part lost its authored UVs) |

| `BUDGET_DRAW_CALLS` | warning | primitives in the exported file exceed `budget.draw_calls` (see `export.merge`) |
| `COLLISION_PROXIES` | warning | more than 32 per-part collision proxies; use `single_hull` or `collision.parts` |
| `LOD_SILHOUETTE` | warning | an LOD file keeps less of LOD0's silhouette than it should in its worst view: LOD1 < 95 %, further LODs < 90 % (export layer) |
| `OP_DECIMATE_LIMITED` / `OP_DECIMATE_OPENED` | warning | decimate stalled above its target / opened a closed surface |
| `TEX_AUTHORED_IMAGE_INVALID` | error | an authored (imported) texture is missing, outside the asset directory or too large |
| `TEX_AUTHORED_UV_MISSING` | error | a part with an authored material lost its UVs (a boolean dropped them) |
| `TEX_AUTHORED_SETS` | info | authored texture sets are exported next to the baked atlas (one material each) |
| `TEX_DENSITY_BELOW_TARGET` | warning | `texel_density` needs a larger atlas than `budget.texture_size` allows |
| `TEX_IMAGE_INVALID` | error | a layer image is missing, outside the asset directory, not an image or too large |
| `TEX_UV_SOURCE_MISSING` | warning | `projection: uv` on geometry without authored UVs; the layer was skipped |
| `TEX_LIFECYCLE` | info / warning | a part's texels were regenerated (`REGION_KEPT`/`RELAYOUT`) or are `INVALID` |
| `PBR_ALBEDO_RANGE` | warning | a non-metal's mean base colour is outside 30..240 sRGB luminance |
| `PBR_METAL_TOO_DARK` | warning | a metal's base colour is darker than real metals |
| `PBR_METALLIC_MIXED` | warning | a material mixes metallic and non-metallic texels over a large area (use 0 or 1) |

Metrics: `uv_overlap`, `uv_utilization`, `texel_density_px_m` (median across
parts at the profile's texture size), `texture` (atlas resolution, target and
achieved px/m, memory). Texture render modes (`sw render --mode`): `textured`,
`albedo`, `roughness`, `metallic`, `texel` (checker at the target density),
`seams`. `sw review` switches to a textured contact sheet when the asset has
textured materials; `sw materials ASSET` renders each material in isolation.

### style (heuristic, warnings only)
| Code | Meaning |
|---|---|
| `STYLE_THIN_FEATURE` | a part's thinnest dimension is below the style's `min_feature_m` (tag `thin_ok` if intended) |
| `STYLE_TOO_MANY_PARTS` | more distinct parts than the style suggests |
| `STYLE_MATERIALS` | more materials than the style suggests |

### export (run by `sw export`)
| Code | Sev | Meaning |
|---|---|---|
| `EXP_GLTF_*` | error/warning | a Khronos glTF-Validator message (code from the validator) |
| `EXP_ROUNDTRIP_PARTS` | error | part nodes missing after re-import |
| `EXP_ROUNDTRIP_TRIS` | error | the triangle count changed on re-import |
| `EXP_ROUNDTRIP_BOUNDS` | error | bounds changed on re-import |
| `EXP_VALIDATOR_UNAVAILABLE` | info | the Node validator is not installed |
| `VALIDATOR_CRASHED` | error | a validator raised; the others still ran (report it as a bug) |

## Pack findings (`sw pack`, informational)

`PACK_MATERIAL_DRIFT` (one material name, several definitions), `PACK_MATERIAL_UNIQUE`,
`PACK_PARAM_DIFFERS` (same param name, different values), `PACK_DENSITY` / `PACK_DENSITY_SPREAD`
(detail density in tris/m², texel density in px/m). They describe a set; they are not errors.

## Adding a validator

```python
@validator("my_rule", "assembly", "One-line description.", ("ASM_MY_CODE",))
def my_rule(asset, surface, metrics):
    return [Issue("ASM_MY_CODE", "warning", "what is wrong", where=part.name, layer="assembly", hint="what to change")]
```

Add a defect-injection test in `tests/test_validation.py` and document the code
here.
