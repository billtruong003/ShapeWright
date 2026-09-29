"""Machine-readable capability manifest, generated from the live registries.

Because it is generated, the manifest can never drift from the code: adding a
shape, op, validator, view, profile or style makes it appear here.
"""

from __future__ import annotations

import yaml

from . import __version__
from .assemble import AXIS_TOKENS, ROOT
from .registry import OPS, SHAPES, load_builtin
from .render.views import MODES, VIEWS
from .source import PART_KEYS, TOP_KEYS
from .validate import VALIDATORS
from .validate import load_builtin as load_validators

COMMANDS = {
    "caps": "list capabilities (this manifest); --json for everything",
    "doc NAME": "details and example for one shape, op, view, mode or issue code",
    "new NAME [--from ASSET]": "scaffold assets/NAME/asset.yaml (optionally as a variant of ASSET)",
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
    "doctor": "check the environment and optional tools",
}


def _named(kind: str) -> dict:
    out = {}
    for p in sorted((ROOT / kind).glob("*.yaml")):
        data = yaml.safe_load(p.read_text()) or {}
        out[p.stem] = data.get("doc", "")
    return out


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
              "EXPORT    glb",
              "", "* = required.  `sw doc NAME` for details, `sw caps --json` for everything."]
    return "\n".join(lines)
