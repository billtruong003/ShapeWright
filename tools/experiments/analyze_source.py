"""Static analysis of an asset source for fresh-agent experiments.

Usage: python tools/experiments/analyze_source.py ASSET_DIR_OR_YAML [--json]

Descriptive metrics (NOT quality scores):
  spatial numbers   literal (non-zero numbers), zero, derived (expressions of params),
                    measured (expressions using measure results), constant-expr (no names)
  parameterization ratio = (derived + measured) / (literal + constant-expr + derived + measured)
  per-part escape profile: component | measured | attached | parametric | literal | composed | mesh_escape
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shapewright import expr  # noqa: E402
from shapewright.assemble import AXIS_TOKENS  # noqa: E402
from shapewright.source import load_source  # noqa: E402

NON_SPATIAL = {
    "type", "doc", "material", "materials", "shading", "smooth_angle", "anchor", "parent", "pivot", "tags", "count",
    "seed", "segments", "sides", "rings", "subdivisions", "points", "iterations", "octaves", "cap_rings", "axis",
    "toward", "radial", "merge", "operation", "enabled", "component", "to", "path", "node", "piece", "z_up",
    "generated_by", "uv", "seams", "share_instances", "frequency", "ratio", "strength", "fraction", "scale", "factor",
    "scale_top", "with", "measure", "angle",
}
ANCHOR_TOKENS = set(AXIS_TOKENS) | {"center"}


def _is_anchor(s: str) -> bool:
    return all(t in ANCHOR_TOKENS for t in s.split("_"))


def classify(value, measure_names: set, out: dict):
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        out["zero" if value == 0 else "literal"] += 1
    elif isinstance(value, str):
        if _is_anchor(value):
            return
        try:
            names = expr.names_in(value)
        except expr.ExprError:
            return
        if not names:
            out["constant_expr"] += 1
        elif names & measure_names:
            out["measured"] += 1
        else:
            out["derived"] += 1
    elif isinstance(value, list):
        for v in value:
            classify(v, measure_names, out)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k in NON_SPATIAL:
                continue
            classify(v, measure_names, out)


def walk_geometry(g, measure_names, out, flags):
    if not isinstance(g, dict):
        return
    if g.get("type") in ("boolean", "combine"):
        flags.add("composed")
    if g.get("type") == "mesh_file":
        flags.add("mesh_escape")
    for k, v in g.items():
        if k in ("base",):
            walk_geometry(v, measure_names, out, flags)
        elif k in ("tools", "items"):
            for t in v or []:
                walk_geometry(t, measure_names, out, flags)
        elif k == "ops":
            for o in v or []:
                if isinstance(o, dict) and isinstance(o.get("shape"), dict):
                    if o["shape"].get("ops"):
                        flags.add("composed")
                    walk_geometry(o["shape"], measure_names, out, flags)
                classify({kk: vv for kk, vv in (o or {}).items() if kk != "shape"}, measure_names, out)
        elif k not in NON_SPATIAL:
            classify(v, measure_names, out)


def analyze(path: Path) -> dict:
    data = load_source(path)
    totals = {"literal": 0, "zero": 0, "constant_expr": 0, "derived": 0, "measured": 0}
    parts = {}
    counts = {"attach": 0, "measure_queries": 0, "components": 0, "arrays": 0, "mirrors": 0, "enabled": 0, "mesh_file": 0}
    for name, raw in (data.get("parts") or {}).items():
        if not isinstance(raw, dict):
            continue
        out = {k: 0 for k in totals}
        flags = set()
        mnames = set((raw.get("measure") or {}).keys())
        counts["measure_queries"] += len(mnames)
        if "component" in raw:
            flags.add("component")
            counts["components"] += 1
            classify(raw.get("with") or {}, set(), out)
        if mnames:
            flags.add("measured")
        if "attach" in raw:
            flags.add("attached")
            counts["attach"] += 1
        counts["arrays"] += "array" in raw
        counts["mirrors"] += "mirror" in raw
        counts["enabled"] += "enabled" in raw
        walk_geometry(raw.get("shape"), mnames, out, flags)
        if "mesh_escape" in flags:
            counts["mesh_file"] += 1
        for k in ("position", "rotate", "attach", "array", "mirror", "ops"):
            if k == "ops":
                walk_geometry({"type": "_", "ops": raw.get("ops")}, mnames, out, flags)
            elif k in raw:
                classify(raw[k], mnames, out)
        nonzero = out["literal"] + out["constant_expr"] + out["derived"] + out["measured"]
        if not flags & {"component", "measured", "attached"}:
            flags.add("parametric" if nonzero and out["literal"] + out["constant_expr"] == 0 else "literal" if nonzero else "parametric")
        parts[name] = {"numbers": out, "profile": sorted(flags)}
        for k in totals:
            totals[k] += out[k]
    denom = totals["literal"] + totals["constant_expr"] + totals["derived"] + totals["measured"]
    params = data.get("params") or {}
    derived_params = sum(1 for v in params.values() if isinstance(v, str) or (isinstance(v, dict) and isinstance(v.get("value"), str)))
    return {
        "asset": str(path),
        "spatial_numbers": totals,
        "parameterization_ratio": round((totals["derived"] + totals["measured"]) / denom, 3) if denom else None,
        "params": {"total": len(params), "derived": derived_params},
        "counts": counts,
        "parts": parts,
        "escape_profile": {k: sum(1 for p in parts.values() if k in p["profile"]) for k in
                           ("component", "measured", "attached", "parametric", "literal", "composed", "mesh_escape")},
    }


if __name__ == "__main__":
    p = Path(sys.argv[1])
    if p.is_dir():
        p = p / "asset.yaml"
    res = analyze(p)
    if "--json" in sys.argv:
        print(json.dumps(res, indent=1))
    else:
        print(f"parameterization_ratio {res['parameterization_ratio']}  numbers {res['spatial_numbers']}")
        print(f"params {res['params']}  counts {res['counts']}")
        print(f"escape_profile {res['escape_profile']}")
        for n, d in res["parts"].items():
            print(f"  {n:24} {','.join(d['profile']):28} {d['numbers']}")
