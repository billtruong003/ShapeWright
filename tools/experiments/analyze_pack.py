"""Pack-level analysis for multi-asset experiments (descriptive, not a score).

Usage: python tools/experiments/analyze_pack.py REPO_SHAPEWRIGHT_DIR asset_a asset_b ... [--json]

Reports: components used (and by how many assets), exact and structural
duplication of part definitions across assets, materials defined per asset and
their colour drift between assets, detail density (triangles per m^2), and
extends/interface usage.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _norm(raw) -> str:
    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in sorted(x.items()) if k not in ("doc",)}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x
    return hashlib.sha1(yaml.safe_dump(strip(raw), sort_keys=True).encode()).hexdigest()[:10]


def _signature(raw) -> str:
    shape = raw.get("shape") or {}
    ops = [o.get("type") for o in (raw.get("ops") or []) + (shape.get("ops") or []) if isinstance(o, dict)]
    return f"{shape.get('type', raw.get('component', '?'))}|{'+'.join(ops)}"


def analyze(root: Path, names: list[str]) -> dict:
    from shapewright.assemble import build
    from shapewright.source import load_source

    exact, struct = defaultdict(list), defaultdict(list)
    comp_use = defaultdict(set)
    mats = defaultdict(dict)
    per_asset = {}
    for n in names:
        path = root / "assets" / n / "asset.yaml"
        raw_file = yaml.safe_load(path.read_text())
        data = load_source(path)
        for pname, praw in (raw_file.get("parts") or {}).items():
            if not isinstance(praw, dict):
                continue
            if "component" in praw:
                comp_use[praw["component"]].add(n)
                continue
            exact[_norm(praw)].append(f"{n}.{pname}")
            struct[_signature(praw)].append(f"{n}.{pname}")
        for mname, m in (data.get("materials") or {}).items():
            mats[mname][n] = str(m.get("base_color", ""))
        a = build(path)
        area = sum(p.mesh.area() for p in a.parts)
        per_asset[n] = {"tris": a.n_tris, "area_m2": round(area, 3), "tris_per_m2": round(a.n_tris / max(area, 1e-9), 1),
                        "size": [round(float(v), 3) for v in a.bounds()[1] - a.bounds()[0]],
                        "extends": bool(raw_file.get("extends")), "interface": bool(data.get("interface")),
                        "parts_defined": len(raw_file.get("parts") or {}), "components_used": sum(1 for p in (raw_file.get("parts") or {}).values() if isinstance(p, dict) and "component" in p)}

    def hexrgb(h):
        h = h.lstrip("#")
        return [int(h[i:i + 2], 16) for i in (0, 2, 4)] if len(h) >= 6 else None

    drift = {}
    for mname, by in mats.items():
        cols = [hexrgb(c) for c in by.values() if hexrgb(c)]
        if len(by) > 1 and cols:
            spread = max(max(c[i] for c in cols) - min(c[i] for c in cols) for i in range(3))
            drift[mname] = {"assets": len(by), "max_channel_spread": spread}
    dens = [v["tris_per_m2"] for v in per_asset.values()]
    comps_dir = root / "components"
    return {
        "assets": per_asset,
        "components_available": sorted(p.stem for p in comps_dir.glob("*.yaml")),
        "component_reuse": {c: sorted(a) for c, a in comp_use.items()},
        "exact_duplicate_parts": {k: v for k, v in exact.items() if len({x.split('.')[0] for x in v}) > 1},
        "structural_duplicates": {k: v for k, v in struct.items() if len({x.split('.')[0] for x in v}) > 2},
        "materials": {m: dict(by) for m, by in mats.items()},
        "material_drift": drift,
        "density_spread": round(max(dens) / max(min(dens), 1e-9), 2) if dens else None,
    }


if __name__ == "__main__":
    root = Path(sys.argv[1])
    names = [a for a in sys.argv[2:] if not a.startswith("--")]
    res = analyze(root, names)
    print(json.dumps(res, indent=1) if "--json" in sys.argv else yaml.safe_dump(res, sort_keys=False, width=140))
