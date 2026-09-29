# AGENTS.md: operating manual for coding agents

You are in **Shapewright**, a 3D modelling environment built for you. You do not
drag vertices or operate a GUI. You **edit a declarative asset source**
(`assets/<name>/asset.yaml`), and the toolchain turns it into geometry, runs
validators, renders inspection images you can look at, records iterations and
exports game-ready GLB files.

Everything runs headless with Python 3.10+. From a fresh clone:

```bash
pip install -r requirements.txt        # numpy scipy trimesh manifold3d xatlas pillow pyyaml fast-simplification
./sw doctor                            # environment check
./sw caps                              # the full modelling vocabulary (generated from code, always current)
```

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
- Geometry expressions nest: a boolean tool can have its own `ops`, `rotate`,
  `translate` and `material`. See `sw doc boolean`.
- Reuse beats copying: `components/` holds sub-assemblies (listed by `sw caps`). `enabled: expr` makes parts optional.
  Variants of a base with an `interface:` may only set its public params.
- Geometry that primitives can't express: produce a mesh file by any means,
  put it in the asset directory and use `{type: mesh_file, path: ...}`, or
  `sw import FILE NAME`. It is validated, rendered and exported like the rest.
- Before any texturing work: `sw uv ASSET lock` and commit `uv.lock.yaml`.
- `mirror: x` creates `<name>_left` / `<name>_right`. `array` creates `<name>_0..n`.
  Refer to instances by those names in `checks` and `--part`.
- Numbers can be expressions: `seat_height - seat_thickness / 2`. Only
  arithmetic, params, `min max abs sqrt sin cos tan atan2 clamp lerp`, and
  `part.size.x`-style metrics inside `checks` are allowed.
- If a validator reports `ASM_FLOATING_PARTS`, the part really does not touch
  anything. Check offsets and anchors in `sw stats` rather than tagging it `floating_ok`.
- `.build/` holds renders and reports. It is disposable and git-ignored, so
  don't commit it. Commit `asset.yaml`, `history/` and, for finished assets,
  `export/`.
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
