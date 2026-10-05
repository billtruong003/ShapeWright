"""`llms.txt`: a one-page brief for any AI agent, generated so it never drifts from the code.

`sw caps --llms` prints it; the committed copy at the repository root is checked by the tests.
"""

from __future__ import annotations

HEADER = """\
# Shapewright

> Agent-native 3D modelling for game assets. You write a declarative YAML asset source (named parts,
> params, checks); deterministic tools build the mesh, validate it in layers, render inspection images
> you look at, and export a game-ready GLB (Godot / Unity / Unreal / generic). Headless: no GPU, no
> display, no Blender. Units metres, +Y up, front +Z, right +X, angles in degrees.

## Install

    pip install "git+https://github.com/billtruong003/ShapeWright"   # or a clone: pip install -r requirements.txt, ./sw
    sw init my_project && cd my_project # optional: a project folder (assets/, packs/, components/)
    sw doctor                          # environment check

Through MCP (Claude Desktop, Cursor, ChatGPT connectors, Claude Code): install with the `[mcp]` extra,
then register the server command `sw mcp` (see docs/MCP.md). Every CLI step below is also an MCP tool.

## The loop (do exactly this)

1. `sw brief "the request"` - closest example asset with full source, profile and budget, rules, vocabulary.
2. `sw new NAME` (or `sw new NAME --from EXAMPLE`) and edit `assets/NAME/asset.yaml`. Set `profile:` to the one
   `brief` suggested (the template says mobile_mid): the profile's budget limits triangles AND materials (table below).
3. `sw review NAME` - validation summary + contact sheet at `assets/NAME/.build/sheet.png`. LOOK at the image.
4. Critique specifically ("leg 0.045 -> 0.07: spindly"), change params first, then parts, then ops.
5. `sw snapshot NAME -m "first version"` BEFORE the first edit, then after each revision
   `sw snapshot NAME -m "what changed" --critique "what you saw"`; `sw compare NAME 1 current`.
6. Stop when: no validation errors, no significant critique left, constraints met (or 6 revisions).
7. `sw export NAME [--target godot|unity|unreal]` -> `assets/NAME/export/NAME.glb` (with a target:
   `NAME_godot.glb` etc.) + `.report.json` (re-import round trip; the Khronos glTF validator too when Node and
   tools/gltf-validator are installed). Report tris vs budget, materials, size, path.
   Engine vs budget: the PROFILE sets the budget (mobile_mid for a mobile game); `--target` (or
   `export: {target: godot}`) only sets the engine packaging, so "mobile, for Godot" = `profile: mobile_mid` + `--target godot`.

## Rules

- Highest abstraction that works: params > placement (`anchor`/`attach`) > ops > new shapes. No vertex lists.
- Placement: `anchor:` is the point of THIS part that lands on `position:` (or on another part's point with
  `attach: {to: PART, at: ANCHOR}`). Anchor names combine `left|right` (x), `bottom|top` (y), `back|front` (z):
  `bottom`, `top_front`, `bottom_back_left`, ... `center` is the default.
- Relationships: `measure:` queries on built parts (section, gap, bounds, anchor, ray), not hand arithmetic.
- Repetition: `array` with `each:`/`skip:`; symmetry: `mirror: x`. Instances are named `<part>_0..n`, `<part>_left/right`.
- Reuse: `components/` (sub-assemblies with public params; they nest), `packs/` (shared params + materials for
  a set), `extends` (variants of one design). A part can place a whole other asset: `asset: NAME` with
  `with: {its own params}` (modular kits: build module assets, then houses from them). Instances (component or
  asset) accept `measure:` (place against measured neighbours) and `pivot:` (one hinged node).
  Check a set with `sw pack --pack NAME`.
- A pack file (`packs/NAME.yaml`): `pack: NAME`, `doc`, `params:` (shared, read-only in members), `materials:`
  (shared palette, read-only), `profile`, `style`, `budget` (defaults a member may override). Members write
  `pack: NAME`; `sw doc NAME` prints a library pack as an example.
- `asset: {placement: floor | wall | ceiling | free}`: floor props rest on y = 0 (default); wall props on the
  plane z = 0 extending toward +Z; `free` for modules and pieces placed by other assets (no grounding checks).
- Surfaces: material archetypes (`wood`, `stone`, `metal`, `painted`, `flat`, `authored`) with semantic params;
  `sw doc wood`. Lock UVs before texture work: `sw uv NAME lock`.
- Try values without editing: `sw validate NAME --set a=1,b=2`; keep one with `sw set NAME a=1`.
- `ASM_FLOATING_PARTS` means the part really floats: fix the placement; `floating_ok` is only for hovering parts.
- Every issue has a code and a hint; `sw doc CODE` explains it. `sw doc PROFILE|STYLE|PACK|COMPONENT` prints that file.
- `extrude` draws the polygon in the XY plane and extrudes along +Z (centred like every shape unless `origin: keep`);
  a `chamfer` on an extrude needs a convex outline.
- `sw doc KEY` explains source keys too (`sw doc pivot`, `sw doc measure`, `sw doc with`).
- Missing capability: produce a mesh file and use `{type: mesh_file}`, or `sw import FILE NAME`.

## Minimal asset

    shapewright: 0.1
    asset: {name: stool, kind: prop/furniture/stool}
    profile: mobile_mid
    style: stylized_lowpoly
    budget: {triangles: 400}
    params:
      height: {value: 0.45, min: 0.35, max: 0.6}
      leg: 0.05
    materials:
      oak: {archetype: wood, color: "#8a5a34"}
    parts:
      seat:
        shape: {type: chamfer_box, size: [0.36, 0.05, 0.36], chamfer: 0.012}
        material: oak
        anchor: top
        position: [0, height, 0]
      leg:
        shape: {type: chamfer_box, size: [leg, height - 0.05, leg], chamfer: 0.006}
        material: oak
        anchor: bottom
        position: [-0.14, 0, -0.14]
        array: [{count: 2, offset: [0.28, 0, 0]}, {count: 2, offset: [0, 0, 0.28]}]   # leg_0_0 .. leg_1_1
    checks:
      - {expr: seat.max.y, min: 0.35, max: 0.6}

"""


def _profiles() -> str:
    import yaml

    from . import paths

    rows = ["## Profiles (budgets per prop; `budget:` in an asset overrides)", "",
            "    profile          triangles  materials  texture  texel px/m  doc"]
    for f in paths.files("profiles"):
        d = yaml.safe_load(f.read_text()) or {}
        b = d.get("budget") or {}
        rows.append(f"    {f.stem:16s} {str(b.get('triangles', '')):>9s}  {str(b.get('materials', '')):>9s}  {str(b.get('texture_size', '')):>7s}"
                    f"  {str(b.get('texel_density', '')):>10s}  {str(d.get('doc', ''))[:60]}")
    return "\n".join(rows) + "\n\n## Capabilities (generated from the code: `sw caps`)\n\n"


def llms_text() -> str:
    from .caps import summary_text

    return HEADER + _profiles() + summary_text().rstrip() + "\n"
