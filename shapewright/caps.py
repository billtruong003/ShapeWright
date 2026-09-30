"""Machine-readable capability manifest, generated from the live registries.

Because it is generated, the manifest can never drift from the code: adding a
shape, op, validator, view, profile or style makes it appear here.
"""

from __future__ import annotations

import yaml

from . import __version__
from . import paths
from .assemble import AXIS_TOKENS
from .registry import OPS, SHAPES, load_builtin
from .render.views import MODES, VIEWS
from .source import PART_KEYS, TOP_KEYS
from .validate import VALIDATORS
from .validate import load_builtin as load_validators

COMMANDS = {
    "brief REQUEST": "start here: closest example asset (with source), profile, rules and vocabulary for a request",
    "workbench [--port N]": "local browser workbench for people over these same commands (127.0.0.1 only)",
    "caps": "list capabilities (this manifest); --json for everything; --llms for the one-page agent brief (llms.txt)",
    "doc NAME": "details and example for one shape, op, view, mode, issue code, profile, style, pack or component",
    "new NAME [--from ASSET]": "scaffold assets/NAME/asset.yaml (optionally as a variant of ASSET)",
    "set ASSET NAME=VALUE": "write param values into the source file, keeping comments (what --set previews)",
    "stats ASSET": "per-part triangles, sizes, positions, materials; sockets; params",
    "validate ASSET": "layered deterministic validation (exit 1 on errors); --json",
    "render ASSET": "images: --view V --mode M --part P [--isolate] or --sheet",
    "review ASSET": "validate + contact sheet + style checklist: the inspection step of the loop",
    "snapshot ASSET -m NOTE [--critique TEXT]": "record an iteration (source + metrics + critique)",
    "log ASSET": "list iterations",
    "compare ASSET A B": "diff two iterations (numbers or 'current'): image + metrics",
    "restore ASSET N": "put iteration N's source back (current source is backed up)",
    "export ASSET": "validate, write GLB, verify with Khronos validator + re-import",
    "variants ASSET --count N": "derive seeded variants from params that declare `vary`",
    "import FILE NAME [--split]": "create an asset from GLB/OBJ/STL/PLY (parts per node/piece; geometry stays in the file)",
    "uv ASSET lock|show": "lock UV regions (uv.lock.yaml) so edits never move other parts' UVs",
    "family ASSET": "validate a base asset and every variant that extends it",
    "pack ASSET... | --pack NAME | --tag TAG": "review assets as one set: common-scale sheet + material/param/density consistency report",
    "materials ASSET": "material sheet: every material on reference shapes, textured + albedo (semantic material review)",
    "bench": "validate every asset under assets/ (CI)",
    "mcp [--transport stdio|streamable-http]": "MCP server: every loop step as a tool, review/render return images (pip install shapewright[mcp])",
    "init [DIR]": "make a folder a project: assets/, packs/, components/, styles/, profiles/ + shapewright.yaml (shadows the library)",
    "doctor": "check the environment and optional tools",
}


def _named(kind: str) -> dict:
    out = {}
    for p in paths.files(kind):
        try:  # one broken file must not take down `sw caps` / `sw doc` for everything (MODULAR_HOUSE_PACK_01)
            data = yaml.safe_load(p.read_text()) or {}
        except yaml.YAMLError as e:
            mark = getattr(e, "problem_mark", None)
            out[p.stem] = f"(unreadable: YAML error{f' at line {mark.line + 1}' if mark else ''}; quote text containing ': ')"
            continue
        out[p.stem] = data.get("doc", "") if isinstance(data, dict) else ""
    return out


POINT_EXAMPLES = {
    "arc": "polygon: [[0.5, 0], [0.7, 0], {arc: {center: [0, 0], radius: 0.7, from: 0, to: 180}}, [-0.5, 0], "
           "{arc: {center: [0, 0], radius: 0.5, from: 180, to: 0}}]   # a round arch ring",
    "helix": "path: [{helix: {radius: 0.05, pitch: 0.02, turns: 4, axis: y}}]   # wound rope, spring, grip wrap",
    "line": "path: [[0, 0, 0], {line: {from: [0, 0.5, 0], to: [0.5, 0.5, 0], segments: 4}}]",
}
PART_FEATURES = {
    "array": {"doc": "Named instances: {count, offset} or {count, radial: x|y|z, angle, start, center}. Optional: "
                     "`each: {translate, rotate, scale}` evaluated per instance with i (0..n-1) and n (rotate/scale about the part's "
                     "anchor point; rand(i) gives a repeatable 0..1 value), `skip: [indices]`. A list of arrays nests (rows x columns): "
                     "names name_i_j. Radial step = angle/count for 360, else angle/(count-1).",
              "example": "array: [{count: 8, offset: [0.2, 0, 0]}, {count: 5, offset: [0, 0.1, 0.15], each: {translate: [\"(i % 2) * 0.1\", 0, 0]}}]"},
    "mirror": {"doc": "x | y | z | {axis, at} | a list of those: twin instances named _left/_right, _bottom/_top, _back/_front.",
               "example": "mirror: [x, z]"},
    "origin": {"doc": "center (default) | keep. keep: the shape keeps its own coordinates (tube paths, strut ends written in asset "
                      "coordinates, including measure results); position becomes an offset; no anchor/attach. strut parts keep by default.",
               "example": "{shape: {type: tube, radius: 0.02, path: [[0, 0, 0], [0, 0.5, 0], [0.4, 0.5, 0]], corner_radius: 0.1}, origin: keep}"},
    "rotate_about": {"doc": "center (default) | anchor: rotate about the unrotated shape's anchor point, which stays where position/attach puts it "
                            "(a leaf tilting about its base, a lid about its hinge edge).",
                     "example": "{anchor: bottom, rotate_about: anchor, rotate: [0, 0, 35], position: [0, 0.3, 0]}"},
}


def manifest() -> dict:
    load_builtin()
    load_validators()
    return {
        "shapewright": __version__,
        "conventions": {"units": "metres", "up": "+Y", "front": "+Z", "right": "+X", "angles": "degrees", "origin": "ground centre (y=0)"},
        "commands": COMMANDS,
        "source_keys": TOP_KEYS,
        "part_keys": PART_KEYS,
        "anchors": {"tokens": sorted(AXIS_TOKENS) + ["center"], "example": "bottom_front_left or [x, y, z] in -1..1"},
        "shapes": {k: v.describe() for k, v in sorted(SHAPES.items())},
        "ops": {k: v.describe() for k, v in sorted(OPS.items())},
        "views": {k: v.doc for k, v in VIEWS.items()},
        "modes": MODES,
        "validators": [{"name": v.name, "layer": v.layer, "doc": v.doc, "codes": list(v.codes)} for v in VALIDATORS],
        "profiles": _named("profiles"),
        "components": _named("components"),
        "packs": _named("packs"),
        "material_archetypes": {k: v.describe() for k, v in sorted(__import__("shapewright.materials", fromlist=["ARCHETYPES"]).ARCHETYPES.items())},
        "measure_queries": __import__("shapewright.spatial", fromlist=["QUERY_KINDS"]).QUERY_KINDS,
        "point_generators": {k: {"doc": v, "example": POINT_EXAMPLES[k]} for k, v in
                             __import__("shapewright.curves", fromlist=["GENERATORS"]).GENERATORS.items()},
        "part_features": PART_FEATURES,
        "styles": _named("styles"),
        "exporters": {"glb": "binary glTF 2.0: named part nodes, hierarchy, materials, UV0, normals, sockets, collision, metadata extras"},
    }


def summary_text() -> str:
    m = manifest()
    lines = [f"shapewright {m['shapewright']}  (units m, +Y up, front +Z, angles in degrees)", "", "COMMANDS"]
    lines += [f"  sw {k:42} {v}" for k, v in m["commands"].items()]
    for fam in ("shapes", "ops"):
        lines += ["", fam.upper()]
        for name, d in m[fam].items():
            params = ", ".join(p + ("" if "default" in spec else "*") for p, spec in d["params"].items())
            lines.append(f"  {name:13} ({params})  {d['doc'][:90]}")
    lines += ["", "VIEWS  " + " ".join(m["views"]), "MODES  " + " ".join(m["modes"]), "",
              "VALIDATION LAYERS  " + " ".join(dict.fromkeys(v["layer"] for v in m["validators"])) + " export",
              "PROFILES  " + " ".join(m["profiles"]), "STYLES    " + " ".join(m["styles"]),
              "COMPONENTS " + (" ".join(m["components"]) or "-") + "   (components/NAME.yaml; use with `component:` in a part)",
              "PACKS     " + (" ".join(m["packs"]) or "-") + "   (packs/NAME.yaml: shared params/materials; `pack: NAME` in an asset)",
              "MATERIALS " + " ".join(m["material_archetypes"]) + "   (material `archetype:` + semantic params; `sw doc wood`; docs/SURFACES.md)",
              "MEASURE   " + " ".join(m["measure_queries"]) + "   (part-level `measure:` queries; docs/RELATIONSHIPS.md)",
              "POINTS    " + " ".join(m["point_generators"]) + "   (items inside any point list: polygon, holes, profile, path; `sw doc arc`)",
              "PARTS     " + " ".join(m["part_features"]) + "   (`sw doc array`: per-instance each/skip/start, nested arrays)",
              "EXPORT    glb; targets " + " ".join(__import__("shapewright.export.targets", fromlist=["TARGETS"]).TARGETS)
              + "   (profiles godot / unity / unreal; asset `export: {target, merge, lods}`; docs/PRODUCTION.md)",
              "", "* = required.  `sw doc NAME` for details, `sw caps --json` for everything."]
    return "\n".join(lines)
