# Asset source format (`asset.yaml`, format 0.1 + hardening additions)

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
| Rotation | `rotate: [rx, ry, rz]` applies X, then Y, then Z, about the part centre. Positive angles follow the right-hand rule (counter-clockwise when looking from the + end of the axis toward the origin): +rx turns +Y toward +Z, +ry turns +Z toward +X, +rz turns +X toward +Y. Example: `rotate: [90, 0, 0]` lays a Y-axis cylinder along -Z...+Z (its top ends up pointing toward +Z) |
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
uv: {method: regions, resolution: 512, padding_px: 4}   # regions (default) | atlas (v0.1) | none
collision: {mode: none | single_box | box | hull}
interface: {params: [...]}       # optional: family contract for variants (docs/FAMILIES.md)
pack: blacksmith                 # optional: member of packs/blacksmith.yaml (shared params/materials; read-only here)
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
  sqrt sin cos tan atan2 clamp lerp rand`, plus the constants `pi tau`.
  `rand(k)` / `rand(k, seed)` is a repeatable pseudo-random number in 0..1 (per-instance variation).
  Nothing else: no strings, no attribute access on numbers, no other calls.
- Params may reference each other in any order. Cycles are reported.
- `min`/`max` produce a `PARAM_OUT_OF_RANGE` warning when violated. `vary` bounds
  are used by `sw variants`.

Params may be `true`/`false` (switches, evaluated as 1/0), e.g. `has_back: true`
with `enabled: has_back` on parts.

**YAML trap:** in flow lists, YAML splits at commas, including commas inside
function calls. Quote such expressions: `rotate: ["-atan2(lean, back_height)", 0, 0]`.
The error message detects this case and says so.

## Materials

```yaml
materials:
  wood: {base_color: "#9a6a40", roughness: 0.85, metallic: 0.0, doc: ...}
  glass: {base_color: "#ffd98a", emissive: "#ffb347", alpha_mode: BLEND, double_sided: true}
```

Colours are sRGB (`"#rrggbb"`, `"#rrggbbaa"` or `[r, g, b]` in 0..1). They are
converted to linear on export.

### Textured materials (archetypes)

A material can name an **archetype**: a procedural recipe with semantic params
(`sw doc wood` lists them with ranges and an example; `sw caps` lists all
archetypes). Available: `flat` (default, untextured), `wood`, `metal`, `stone`,
`painted`.

```yaml
materials:
  oak:   {archetype: wood, color: "#8a5a36", grain_strength: 0.35, grain_scale: 0.03, edge_wear: 0.3}
  iron:  {archetype: metal, color: "#5a5f66", roughness: 0.5, edge_wear: 0.5, rust: 0.2}
  oak_light: {use: oak, color: "#b08050"}     # instance: inherits oak, overrides colour
  sign:  {archetype: painted, color: "#3f6b8a", under_color: "#6b4a30", chips: 0.5,
          layers: [{image: textures/emblem.png, projection: triplanar, scale: 0.4, opacity: 0.8}]}
```

- Common params on every archetype: `color`, `roughness`, `edge_wear` (0..1,
  scuffed convex edges), `edge_color`, `edge_width` (m), `seed`, `grime` (0..1,
  dirt near the asset's base and in creases within a part), `grime_color`, `grime_height` (m).
- Patterns are evaluated **per part**: wood grain runs along each part's longest
  axis and every part gets its own variation. Model planks as separate parts
  (for example with `array`/`mirror`) if each plank should show its own grain.
  Parts sharing UVs (`uv: {share_instances: true}`) also share their texels.
- `use: NAME` makes an instance of another material in the same asset (or pack).
- `layers:` stack on top of the archetype: `image: path` (inside the asset
  directory) or `vertex_color: true`, with `projection: triplanar | uv`,
  `scale` (m per tile, triplanar), `opacity`, `mask: none | edge | inverse_edge`, `tint`.
  `projection: uv` needs authored UVs (a `mesh_file` part); otherwise the layer is
  skipped with `TEX_UV_SOURCE_MISSING`.
- Textures are evaluated in object space (continuous across UV seams) and baked
  into the UV0 atlas: base colour (sRGB) + ORM (occlusion/roughness/metallic).
  Atlas size follows `uv: {texel_density: PX_PER_M}` (default 256), capped by
  `budget.texture_size` (`TEX_DENSITY_BELOW_TARGET` when the cap wins).
- An asset whose materials are all `flat` without edge wear or layers exports no
  textures, exactly as before. The legacy `base_color:` key still works as `color:`.
- Lock UVs (`sw uv ASSET lock`) before texturing so part edits don't move texels.
  Design: docs/SURFACES.md.

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

### Geometry expressions (recursive)

`shape:` takes a **geometry expression**, and so does everything else that
expects geometry (boolean tools, `boolean.base/tools`, `combine.items`):

```yaml
{type: <generator>, <generator params>..., ops: [...], material: m, rotate: [rx, ry, rz], translate: [x, y, z]}
```

evaluated as `generator → centre → ops → rotate → translate`. So a tool can have its own ops:

```yaml
shape:
  type: boolean
  operation: difference
  base: {type: chamfer_box, size: [0.4, 0.3, 0.3], ops: [{type: taper, scale: 0.8}]}
  tools:
    - {type: cylinder, radius: 0.08, height: 0.5, rotate: [90, 0, 0], material: iron, ops: [{type: taper, scale: 0.6}]}
```

`material` on an expression sets the material of the faces it creates (inner
expressions keep theirs). Parts can then have several materials (one glTF
primitive each). `mirror` and `repeat` also exist as **ops** (copies stay in
one part), distinct from part-level `mirror:`/`array:` (named instances).

### Build order inside a part

```
measure → shape expression → centre → part ops → rotate → place (position | attach) → array (+ each) → mirror
```

`origin: keep` skips the centring: the shape stays where its own coordinates put it (tube
paths and strut ends written in asset coordinates, including `measure` results), and
`position` is an offset. `strut` parts keep their origin by default.
`rotate_about: anchor` rotates about the unrotated shape's anchor point, and that point is
what `position`/`attach` places (a leaf tilting about its base). By default the part rotates
about its centre and the rotated bounding box's anchor is placed.

### Measure: relationships from real geometry

```yaml
measure:
  post: {section: rear_leg_right, axis: y, at: rail_y}                          # min/max/center/size
  span: {gap: [front_leg_left, front_leg_right], axis: x, section: {axis: y, at: 0.2}}   # start/end/length/center
  box:  {bounds: seat}
  pt:   {anchor: seat, at: top_back}
  hit:  {ray: seat, from: [0, 2, 0], dir: [0, -1, 0]}                          # x/y/z/distance
position: [span.center, 0.2, post.center.z]
```

Queries see parts built earlier (ordering is automatic). See docs/RELATIONSHIPS.md.

### Optional parts and components

```yaml
top_rail: {enabled: has_back, ...}          # not built when false
top:
  component: plank_top                       # components/plank_top.yaml
  with: {length: 1.2, width: 0.3, planks: 2} # public params only
  materials: {top: wood, under: wood_dark}   # map component material slots
  anchor: top
  position: [0, 0.45, 0]
```

Component parts are named `<instance>_<part>` (`top_plank_0`); the group is
addressable as `top`. See docs/FAMILIES.md.

### Baked and imported geometry

```yaml
shape: {type: mesh_file, path: source/rock.glb, node: Rock_LOD0, piece: -1, scale: 1, z_up: false,
        generated_by: "blender --background -P make_rock.py"}   # recorded, never executed
tags: [open_ok]   # if the file is not watertight
```

Paths must stay inside the asset directory (GLB, OBJ, STL, PLY). Authored UVs
and vertex colours are kept. `sw import FILE NAME [--split]` writes such a
source for you. It also writes one **`authored`** material per file material, with its textures
(base colour, metallic-roughness, normal, occlusion, emissive) saved under `source/textures/`:

```yaml
materials:
  bottle_mat: {archetype: authored, textures: {base_color: source/textures/bottle_mat_base_color.png,
               normal: source/textures/bottle_mat_normal.png}, color: "#ffffff", roughness: 1.0, metallic: 1.0}
```

- Parts with an authored material keep their own UVs and textures, which pass through to the export
  unchanged. They are not baked and take no atlas space.
- UV overlap and tiling are the author's business on those parts.
- To re-surface an imported part, give it a procedural material (`archetype: wood`, ...). It is then
  baked into the asset atlas through its authored UVs.
- Ops that rebuild topology (booleans) drop authored UVs (`TEX_AUTHORED_UV_MISSING`).
- `decimate` and `clean` keep them.
- Repair ops for imported geometry: `{type: clean}` welds vertices, drops zero-area and duplicate
  faces, fixes winding, and can `fill_holes: true`.

See docs/IMPORT.md.

### Packs (sets of assets)

`packs/NAME.yaml` holds `pack`, `doc`, `params`, `materials`, `profile`, `style`, `budget`. A member asset
writes `pack: NAME` (or a relative `.yaml` path). The pack's params and materials are merged in and are
**read-only**: redefining one is `PACK_OVERRIDE`. The profile and style are the pack's; budget keys are
defaults a member may override. `sw pack --pack NAME` reviews all members together at a common scale.

### Replicating component instances

`mirror:` and `array:` on a component instance replicate the whole placed group. Instances are named
`<instance>_left` / `<instance>_0`, and their parts `<instance>_left_<part>`.

### Per-part UV settings

```yaml
uv: {share_instances: true, seams: regions}   # see docs/UV.md
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
instance (`front_leg_left`), or `origin`. The same holds for `measure` targets: a
source-part name does not change when a count changes, while `row_2_front` may stop
existing. Attachments are resolved in
dependency order, and cycles are errors.

### Replication

```yaml
array: {count: 3, offset: [0.1, 0, 0]}               # names: slat_0, slat_1, slat_2
array: {count: 8, radial: y, angle: 360, center: [0, 0, 0]}   # center is in WORLD coordinates
mirror: x                                            # across the plane x = 0
mirror: [x, z]                                       # 4 instances: post_front_left, ...
mirror: {axis: y, at: height / 2}                    # across y = height/2 (top/bottom twins)
mirror: [z, {axis: y, at: size / 2}]
```

Arrays vary per instance with `each:`, evaluated for every instance with `i` (0..n-1) and
`n`. `rotate`/`scale` act about the part's anchor point, then `translate`, then the
array step. `skip:` leaves slots out, `start:` offsets a radial array's first angle, and a
**list** of arrays nests them (names `name_i_j`):

```yaml
array: {count: 10, radial: y, start: 12, each: {rotate: [0, 0, "-25 - 30 * rand(i)"], scale: [1, "0.8 + 0.4 * rand(i, 7)", 1]}}
array: {count: 9, radial: z, angle: 180, center: [0, spring_y, 0], skip: [4]}      # voussoirs without the keystone slot
array: [{count: 8, offset: [0.25, 0, 0]}, {count: 6, offset: [0, 0.12, -0.16], each: {translate: ["(i % 2) * 0.125", 0, 0]}}]
```

Radial step: `angle / count` for a full 360°, else `angle / (count - 1)` (both ends included).

Mirror suffixes are chosen by side: `_left/_right` (x), `_bottom/_top` (y),
`_back/_front` (z), ordered z then y then x (`_front_left`). The array is
applied before the mirror (`slat_0_left`).

## Shapes and ops

Run `sw caps` for the list and `sw doc NAME` for the parameters and an example.
Families (v0.1):

- **Primitives:** `box`, `chamfer_box`, `cylinder` (also frustum and cone,
  optional rim chamfer), `sphere`, `icosphere`, `capsule`, `torus`, `ring`
- **Composition:** `boolean` (base + tools, any operation), `combine` (several shells in one part)
- **Sources:** `mesh_file` (baked/imported/external geometry)
- **Profiles:** `lathe` (open profile around Y), `revolve` (closed outline
  around Y), `extrude` (2D polygon with holes, taper, and `chamfer` for convex
  outlines), `tube` (sweep along a 3D path, optional radius taper, `corner_radius`
  rounds every bend: pipe elbows, bent handles)
- **Members:** `strut` (a beam/brace/rod from a `from` point to a `to` point; box or round
  section; keeps asset coordinates, so its ends can be `measure` results)
- **Procedural:** `random_hull` (seeded)
- **Ops:** `scale rotate translate` · `taper bend twist shear` · `jitter noise inflate` ·
  `subdivide smooth decimate` · `subtract union intersect flat_bottom` · `mirror repeat`

### Point lists: arcs, helices, lines

Every list of points (`extrude.polygon`/`holes`, `lathe.profile`, `revolve.polygon`,
`tube.path`) may contain **generators** that expand in place, mixed with literal points:

```yaml
polygon: [[0.5, 0], [0.7, 0], {arc: {center: [0, 0], radius: 0.7, from: 0, to: 180}}, [-0.5, 0],
          {arc: {center: [0, 0], radius: 0.5, from: 180, to: 0}}]           # a round arch ring
path: [{helix: {radius: 0.05, pitch: 0.02, turns: 4, axis: y}}]            # wound rope, spring, wrap
path: [[0, 0, 0], {arc: {center: [0.3, 0, 0], radius: 0.3, from: 180, to: 90, plane: xy, radius_end: 0.2}}]  # a curl
```

`arc` angles are degrees counter-clockwise from the plane's first axis; `radius_end` makes a
spiral and `rise` a ramp. `sw doc arc`, `sw doc helix`, `sw doc line`.

Boolean ops take a nested shape as the tool:

```yaml
ops:
  - {type: subtract, shape: {type: box, size: [0.14, 0.2, 0.3]}, position: [0, 0, 0], rotate: [0, 45, 0]}
```

The tool is centred after its own ops, so `position` places the centre of the tool's
final bounding box (after its `mirror`/`repeat` ops), in the part's local space.

## Sockets

```yaml
sockets:
  sit_point: {attach: {to: seat, at: top, offset: [0, 0, 0.03]}, rotate: [0, 0, 0], doc: ...}
```

Exported as empty nodes `SOCKET_<name>` with `extras.socket`. `attach.to: origin`
places a socket relative to the asset origin.

## Checks: design intent as tests

```yaml
checks:
  - {expr: seat.max.y, min: 0.42, max: 0.50, doc: comfortable seat height}
  - {expr: top_rail.size.x / seat.size.x, min: 0.8, max: 1.15}
  - {expr: glass.center.z > 0.3, doc: lantern hangs clear of the post}
  - {expr: asset.height, min: height - 0.05, severity: warning}
```

`when: <expr>` makes a check conditional (`{expr: asset.height, min: 0.85, when: has_back}`).

The namespace contains all params plus metrics:
`asset`, every part instance (`front_leg_left`), every source part (`front_leg`,
the union of its instances) and every component instance (`top`). Repeated parts
also expose `count`, `first` and `last` (instances in build order), for example
`{expr: tread.last.max.y, min: steps * rise - 0.01}` when the count is a param. Each exposes `min`, `max`, `center`, `size`
(each with `.x .y .z`), `width`, `height`, `depth` and `triangles`. Bounds may be
expressions. A failing check is a `CHECK_FAILED` error unless `severity: warning`.

## Inheritance (`extends`) and family interfaces

If the base declares `interface: {params: [...]}`, a variant may set only those
params (plus asset/budget/profile/style/materials/uv/collision/notes), and its
`checks` are *added* to the base's. Without an interface, the rules below apply
(v0.1 behaviour, flagged with `FAMILY_NO_INTERFACE`).

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
