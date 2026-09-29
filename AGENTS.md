# AGENTS.md: operating manual for coding agents

You are in **Shapewright**, a 3D modelling environment built for you. You do not
drag vertices or operate a GUI. You **edit a declarative asset source**
(`assets/<name>/asset.yaml`), and the toolchain turns it into geometry, runs
validators, renders inspection images you can look at, records iterations and
exports game-ready GLB files.

Everything runs headless with Python 3.10+. From a fresh clone:

```bash
pip install -r requirements.txt        # numpy scipy trimesh manifold3d xatlas pillow pyyaml fast-simplification
./sw brief "the user's request"        # START HERE: closest example asset (full source), profile and budget,
                                       # rules for this kind of prop, vocabulary with docs, in one call
./sw doctor                            # environment check (only if something fails)
./sw caps                              # the full modelling vocabulary (generated from code, always current)
```

`sw brief` is usually all the reading you need before writing a first version. Consult
`docs/ASSET_FORMAT.md` and `sw doc NAME` when you need a specific key or shape.

Optional: `cd tools/gltf-validator && npm install` enables the Khronos glTF
validator during `sw export`.

## The loop

```
understand -> plan -> write asset.yaml -> sw review -> LOOK at the sheet -> critique
     ^                                                                       |
     +--- sw snapshot (note + critique) <- edit params/parts <---------------+
                              ... until done ... -> sw export
```

1. **Understand the request.** Extract hard constraints (triangle budget,
   platform, dimensions) and soft ones (style, mood). Pick a `profile:`
   (`sw caps` lists them) and a `style:`.
2. **Plan in parts, not polygons.** List the semantic parts (seat, front_leg,
   rear_leg, ...), their real-world dimensions in metres, and how they attach.
   Name every meaningful dimension as a `param`. Write design intent as
   `checks:` (for example seat height 0.42–0.50 m). Look at a benchmark asset
   of a similar kind in `assets/` first; copying its structure is encouraged.
3. **Create.** `./sw new my_asset` scaffolds a source, or `./sw new my_variant --from tavern_chair`
   inherits one. Format: `docs/ASSET_FORMAT.md`.
4. **Inspect.** `./sw review my_asset` prints the validation summary and writes
   `assets/my_asset/.build/sheet.png` (front/right/top orthographic,
   3/4 views, part colours, wireframe, UV layout). **Open the image and look at
   it.** Orthographic views have metric scale bars, so read proportions off them.
   Zoom into a part with `./sw render my_asset --part backrest --view front`.
5. **Validate.** Errors are defects to fix. Every issue names a code, the part or
   source path, and a hint. Codes are explained in `docs/VALIDATION.md`.
6. **Critique specifically.** Write findings as *part.param → change, reason*,
   for example: `back_slat: 3 thin slats read as modern -> 2 wide slats (style wants fewer, larger forms)`.
   Never write "looks bad". Use `./sw stats` for exact part sizes.
7. **Revise.** Change params first, then parts, and write custom geometry last.
   Record each meaningful step with
   `./sw snapshot my_asset -m "what changed" --critique "what you saw"`.
   Compare iterations with `./sw compare my_asset 1 current` (side-by-side image,
   silhouette diff, per-part size changes).
8. **Stop** when all of these hold: no validation errors, your last critique
   has no significant findings, and the user's constraints are met. Also stop
   when the iteration budget is spent (default: 6 revisions) or when two
   consecutive revisions stop improving. Say which condition stopped you.
9. **Export.** `./sw export my_asset` writes `assets/my_asset/export/my_asset.glb`
   and a report (Khronos validation plus re-import round-trip). Report the final
   metrics to the user: triangles vs budget, size, materials, validation
   status, file path.

## Rules that save you time

- **Units are metres. +Y is up, the front faces +Z, right is +X.** Angles are in degrees.
  Assets rest on y = 0, with the origin under the grounded parts.
- Use the **highest abstraction that works**: params, then placement
  (`attach`/`anchor`), then ops, then new shapes. Never hand-write vertex lists
  when a shape or op exists.
- Anchors are compositional names: `top`, `bottom_front_left`, `right`, ...
  `attach: {to: seat, at: bottom_front_right, offset: [...]}` places this part's
  `anchor:` point on the other part's anchor.
- **Don't re-derive another part's geometry with arithmetic.** Use `measure:`
  queries on parts built earlier (`section` of a leaning post at a height,
  `gap` between two legs, `ray` onto a surface). See docs/RELATIONSHIPS.md.
  If a relationship would need hand-maths, that is a sign to measure instead.
- **Don't compute curves by hand.** Arcs, spirals and helices are point generators inside any point
  list (`{arc: ...}`, `{helix: ...}`; `sw doc arc`); pipe bends are `tube` `corner_radius`; a beam
  between two points is a `strut` (ends may be `measure` results). Instances that differ (rows offset
  by half, leaves at varying angles, a skipped keystone slot) are one `array` with `each:`/`skip:`
  (`sw doc array`), not hand-numbered parts. Tilting about a base or hinge: `rotate_about: anchor`.
- Geometry expressions nest: a boolean tool can have its own `ops`, `rotate`,
  `translate` and `material`. See `sw doc boolean`.
- Several assets that must look like one set: create `packs/NAME.yaml` (shared scale, construction
  params, palette) and put `pack: NAME` in each asset; review the set with `sw pack --pack NAME`.
  Don't use `extends` for this: `extends` is for variants of one design.
- Reuse beats copying: `components/` holds sub-assemblies (listed by `sw caps`); component instances can
  be `mirror`ed and `array`ed like parts. `enabled: expr` makes parts optional.
  Variants of a base with an `interface:` may only set its public params.
- Geometry that primitives can't express: produce a mesh file by any means,
  put it in the asset directory and use `{type: mesh_file, path: ...}`, or
  `sw import FILE NAME`. It is validated, rendered and exported like the rest.
- Imported assets keep their materials and textures (`archetype: authored`). Rename parts from a
  `--mode parts` render. Repair them with `{type: clean}` and reduce them with `{type: decimate}`;
  both keep the UVs. Replace a piece by deleting it and adding a native part. Assign a procedural
  material only to parts whose look you want to change. docs/IMPORT.md.
- Surface detail comes from material **archetypes**, not geometry or hand-made images:
  `materials: {oak: {archetype: wood, color: ..., grain_strength: ..., edge_wear: ...}}`.
  `sw doc wood` (or metal, stone, painted, flat) lists the params. Look at the result
  with `sw materials ASSET` and `sw render ASSET --mode textured`; critique in terms of
  params ("grain too busy -> grain_scale 0.03 -> 0.05"). "Used/dirty" is `grime`, "handled" is `edge_wear`.
- Before any texturing work: `sw uv ASSET lock` and commit `uv.lock.yaml`.
- To prove an asset stays correct when its params change, try values without
  editing the file: `sw validate ASSET --set steps=14,rise=0.2` (also works on
  `review`, `render`, `stats`). Keep a value with `sw set ASSET steps=14` (edits only that value;
  comments stay; refuses values outside min/max). Keep permanent variants as `extends` files and
  check them with `sw family`.
- `mirror: x` creates `<name>_left` / `<name>_right`. `array` creates `<name>_0..n`.
  Refer to instances by those names in `checks` and `--part`.
- Numbers can be expressions: `seat_height - seat_thickness / 2`. Only
  arithmetic, params, `min max abs sqrt sin cos tan atan2 clamp lerp`, and
  `part.size.x`-style metrics inside `checks` are allowed.
- If a validator reports `ASM_FLOATING_PARTS`, the part really does not touch
  anything; the message says how far it is from the nearest part. Fix offsets and anchors (`sw stats`)
  rather than tagging it `floating_ok`, which is only for parts meant to hover. A tagged part that sits
  within a few cm of the asset still gets `ASM_FLOATING_TAGGED_NEAR`.
- Every asset in `assets/` is a regression benchmark: a new asset needs its geometry hash recorded with
  `python3 tests/update_golden.py` before `pytest` passes.
- People can work on the same assets with `sw workbench` (a local browser page). Every button runs an
  `sw` command and shows it, so their changes are ordinary source edits and history entries you can read.
- `.build/` holds renders and reports. It is disposable and git-ignored, so
  don't commit it. Commit `asset.yaml`, `history/` and, for finished assets,
  `export/`.
- **Shipping to an engine:** use `profile: godot | unity | unreal` (or `export: {target: ...}`). The target
  names collision so the engine builds physics (`collision: {mode: single_hull}` for a simple prop),
  merges static parts into one primitive per material (draw calls), keeps each part with a `pivot`
  (hinged lid, wheel) as its own node with its children, and writes LOD files where the engine
  needs them. docs/PRODUCTION.md.
- If something you need is missing (a shape, op or validator), add it to the
  framework rather than hacking the asset. See `CONTRIBUTING.md`. One decorated
  function becomes available everywhere.

## Error recovery

| Symptom | Do this |
|---|---|
| `FAIL (asset source could not be built)` | Read the `where` path and the `->` hint. Typos come with suggestions. |
| `OP_FAILED` in a boolean | Both shapes must be closed. Check the tool position and that the cut doesn't remove everything. |
| A revision made things worse | `./sw compare A current`, then `./sw restore A` (the current source is backed up in `.build/`). |
| Triangle budget exceeded | The error lists the heaviest parts. Lower `segments`, drop parts or subdivisions, or use `decimate`. |
| Command hangs or is slow | Limits are in `shapewright/limits.py`. The CLI aborts after 120 s. |

## Map of the repository

| Path | What |
|---|---|
| `assets/` | benchmark assets. Read `tavern_chair` first; its `history/` shows a real critique loop |
| `shapewright/ops/` | shapes, modifiers, composition (`boolean`, `combine`), `mesh_file` |
| `components/` | reusable sub-assemblies with public params |
| `shapewright/backend.py` | the only module that touches geometry libraries |
| `shapewright/spatial.py` | `measure` queries |
| `shapewright/assemble.py` | parts, anchors, attach, mirror/array, sockets: source → semantic scene |
| `shapewright/surface.py` | normals, UVs (xatlas), vertex buffers |
| `shapewright/validate/` | layered validators |
| `shapewright/render/` | deterministic CPU renderer, views, contact sheets |
| `shapewright/export/` | GLB writer and export verification |
| `profiles/`, `styles/` | production budgets and art-direction profiles |
| `docs/` | vision, research, architecture, capability map, validation, format, workflow, roadmap; MESH_MODEL, BACKEND, RELATIONSHIPS, UV, FAMILIES; DESIGN_REVIEW and HARDENING (history) |
