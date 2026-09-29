# Asset source format (`asset.yaml`, format 0.1)

An asset is a directory with one `asset.yaml`. The file is YAML (comments
welcome), parsed with `safe_load`. Unknown keys are errors with "did you mean"
suggestions. `sw caps --json` lists every shape, op and parameter with types
and defaults. This document explains the structure.

## Conventions

| | |
|---|---|
| Units | metres |
| Axes | +Y up, the **front of the asset faces +Z**, right is +X (glTF convention; no conversion on export) |
| Angles | degrees everywhere, including `sin`/`cos`/`tan`/`atan2` in expressions |
| Origin | on the ground (y = 0), horizontally under the parts that rest on the ground |
| Side names | `left` = -X, `right` = +X, `back` = -Z, `front` = +Z, `bottom` = -Y, `top` = +Y (world directions, not the object's "own" left) |

## Top level

```yaml
shapewright: 0.1                 # format version
extends: ../tavern_chair         # optional: inherit another asset's source (deep merge)
asset: {name, kind, description, tags, placement}
profile: mobile_mid              # production profile (profiles/NAME.yaml)
style: stylized_lowpoly          # style profile (styles/NAME.yaml)
budget: {triangles: 700, materials: 2}   # overrides the profile's budget
params: {...}
materials: {...}
parts: {...}
sockets: {...}
checks: [...]
uv: {method: auto, resolution: 512, padding_px: 4}
collision: {mode: none | single_box | box | hull}
notes: free text
```

`asset.placement` is `floor` (default: must rest on y = 0), `wall`, `ceiling` or
`free`. Only `floor` enforces grounding.

## Params and expressions

```yaml
params:
  seat_height: {value: 0.46, min: 0.40, max: 0.50, doc: top of the seat, vary: [0.44, 0.48]}
  leg: 0.07                               # shorthand for {value: 0.07}
  leg_x: seat_width / 2 - leg_inset - leg / 2   # derived (expression)
```

- Any numeric field anywhere can be a number or an **expression string**.
  YAML bare words become strings, so `size: [seat_width, 0.05, seat_depth]` works.
- Expression language: numbers, param names, `+ - * / // % **`, comparisons,
  `a if cond else b`, `and/or/not`, and the functions `min max abs round floor ceil
  sqrt sin cos tan atan2 clamp lerp`, plus the constants `pi tau`.
  Nothing else: no strings, no attribute access on numbers, no other calls.
- Params may reference each other in any order. Cycles are reported.
- `min`/`max` produce a `PARAM_OUT_OF_RANGE` warning when violated. `vary` bounds
  are used by `sw variants`.

## Materials

```yaml
materials:
  wood: {base_color: "#9a6a40", roughness: 0.85, metallic: 0.0, doc: ...}
  glass: {base_color: "#ffd98a", emissive: "#ffb347", alpha_mode: BLEND, double_sided: true}
```

Colours are sRGB (`"#rrggbb"`, `"#rrggbbaa"` or `[r, g, b]` in 0..1). They are
converted to linear on export.

## Parts

```yaml
parts:
  rear_leg:                       # identifier; becomes the node name (plus instance suffixes)
    doc: rear legs continue upward as backrest posts
    shape: {type: chamfer_box, size: [leg, back_height, leg], chamfer: 0.01}
    ops:                          # ordered modifiers in part-local space
      - {type: shear, axis: y, toward: z, amount: -lean}
      - {type: jitter, amount: wear, seed: 3}
    rotate: [0, 0, 0]             # degrees X, then Y, then Z, about the part centre, after ops
    anchor: bottom_front          # which point of THIS part is placed
    position: [leg_x, 0, post_z]  # ...at this world position   (or use attach)
    mirror: x                     # twins: rear_leg_left, rear_leg_right
    material: wood_dark
    shading: auto                 # flat | smooth | auto (auto-smooth by angle)
    smooth_angle: 40
    parent: seat                  # semantic hierarchy in the exported node tree
    pivot: bottom                 # exported node origin (default: asset origin)
    tags: [structural]            # free tags; `floating_ok`, `thin_ok` silence validators
```

### Build order inside a part

```
shape → centre on bounding box → ops (in order) → rotate → place (position | attach) → array → mirror
```

### Anchors

An anchor is a point on the part's axis-aligned bounding box, named by combining
tokens: `center`, `top`, `bottom`, `left`, `right`, `front`, `back`. For example
`bottom_front_left` is the lower, front, left corner, and `top` is the centre of
the top face. An explicit `[x, y, z]` in -1..1 box coordinates also works.

### Placement

```yaml
position: [x, y, z]                          # absolute world position of `anchor`
attach: {to: seat, at: bottom_front_right, offset: [dx, dy, dz]}
                                             # put `anchor` on another part's anchor (+ offset)
```

`to` may name a source part (its placement before mirroring or arraying) or an
instance (`front_leg_left`), or `origin`. Attachments are resolved in
dependency order, and cycles are errors.

### Replication

```yaml
array: {count: 3, offset: [0.1, 0, 0]}               # names: slat_0, slat_1, slat_2
array: {count: 8, radial: y, angle: 360, center: [0, 0, 0]}
mirror: x                                            # across the plane x = 0
mirror: [x, z]                                       # 4 instances: post_front_left, ...
mirror: {axis: y, at: height / 2}                    # across y = height/2 (top/bottom twins)
mirror: [z, {axis: y, at: size / 2}]
```

Mirror suffixes are chosen by side: `_left/_right` (x), `_bottom/_top` (y),
`_back/_front` (z), ordered z then y then x (`_front_left`). The array is
applied before the mirror (`slat_0_left`).

## Shapes and ops

Run `sw caps` for the list and `sw doc NAME` for the parameters and an example.
Families (v0.1):

- **Primitives:** `box`, `chamfer_box`, `cylinder` (also frustum and cone,
  optional rim chamfer), `sphere`, `icosphere`, `capsule`, `torus`, `ring`
- **Profiles:** `lathe` (open profile around Y), `revolve` (closed outline
  around Y), `extrude` (2D polygon with holes and taper), `tube` (sweep along a
  3D path, optional radius taper)
- **Procedural:** `random_hull` (seeded)
- **Ops:** `scale rotate translate` · `taper bend twist shear` · `jitter noise inflate` ·
  `subdivide smooth decimate` · `subtract union intersect flat_bottom`

Boolean ops take a nested shape as the tool:

```yaml
ops:
  - {type: subtract, shape: {type: box, size: [0.14, 0.2, 0.3]}, position: [0, 0, 0], rotate: [0, 45, 0]}
```

## Sockets

```yaml
sockets:
  sit_point: {attach: {to: seat, at: top, offset: [0, 0, 0.03]}, rotate: [0, 0, 0], doc: ...}
```

Exported as empty nodes `SOCKET_<name>` with `extras.socket`.

## Checks: design intent as tests

```yaml
checks:
  - {expr: seat.max.y, min: 0.42, max: 0.50, doc: comfortable seat height}
  - {expr: top_rail.size.x / seat.size.x, min: 0.8, max: 1.15}
  - {expr: glass.center.z > 0.3, doc: lantern hangs clear of the post}
  - {expr: asset.height, min: height - 0.05, severity: warning}
```

The namespace contains all params plus metrics:
`asset`, every part instance (`front_leg_left`) and every source part (`front_leg`,
the union of its instances). Each exposes `min`, `max`, `center`, `size`
(each with `.x .y .z`), `width`, `height`, `depth` and `triangles`. Bounds may be
expressions. A failing check is a `CHECK_FAILED` error unless `severity: warning`.

## Inheritance (`extends`)

```yaml
extends: ../tavern_chair
asset: {name: tavern_stool}
params: {seat_width: 0.38, back_height: seat_height - seat_thickness + 0.02}
parts:
  top_rail: null          # delete an inherited part
  rear_leg: {anchor: bottom, position: [leg_x, 0, post_z]}   # merge into the inherited part
checks: [...]             # lists replace, they don't merge
```

Mappings deep-merge, lists and scalars replace, and `null` deletes.

## Profiles and styles

`profiles/*.yaml`: `doc`, `budget` (`triangles`, `materials`, `texture_size`,
`texel_density`), `uv.padding_px`, `export.collision_naming` (`ucx` | `godot`).

`styles/*.yaml`: `doc`, `description` (art direction in prose, printed by
`sw review`), `shading` defaults, `heuristics` (`min_feature_m`, `max_parts`,
`max_materials`; warnings only), `palette`, and `review` (questions the agent
answers when looking at the sheet).

An asset directory may contain its own `profiles/` or `styles/` folder, which
takes precedence over the repository's.
