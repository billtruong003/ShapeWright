"""Surface metrics for fresh-agent experiments (Phase 8+).

Usage: python tools/experiments/analyze_surface.py ASSET_DIR [--json]

Descriptive, not quality scores:
  per material   archetype, params set explicitly vs left at defaults, `use:` instance, layers
  escape profile image files in the asset directory (hand-made textures), image layers,
                 flat materials on textured assets
  bake           atlas resolution, target vs achieved px/m, lifecycle states, TEX_*/PBR_* issues
  history        material-param edits between consecutive snapshots
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shapewright.assemble import build  # noqa: E402
from shapewright.bake import textures_for  # noqa: E402
from shapewright.surface import build_surface  # noqa: E402
from shapewright.validate.run import run_validation  # noqa: E402

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".webp"}


def _materials(path: Path) -> dict:
    try:
        return (yaml.safe_load(path.read_text()) or {}).get("materials") or {}
    except (OSError, yaml.YAMLError):
        return {}


def material_edits(asset_dir: Path) -> list:
    snaps = sorted((asset_dir / "history").glob("*/asset.yaml"), key=lambda p: p.parent.name)
    seq = [*snaps, asset_dir / "asset.yaml"]
    out = []
    for a, b in zip(seq, seq[1:]):
        ma, mb = _materials(a), _materials(b)
        changed = []
        for name in sorted(set(ma) | set(mb)):
            x, y = ma.get(name) or {}, mb.get(name) or {}
            if not isinstance(x, dict) or not isinstance(y, dict):
                changed.append(f"{name}: (redefined)")
                continue
            changed += [f"{name}.{k}: {x.get(k)} -> {y.get(k)}" for k in sorted(set(x) | set(y)) if x.get(k) != y.get(k)]
        out.append({"from": a.parent.name, "to": b.parent.name, "changes": changed})
    return out


def analyze(asset_dir: Path) -> dict:
    asset = build(asset_dir)
    surface = build_surface(asset)
    tex = textures_for(asset, surface)
    report = run_validation(asset, surface)
    raw = _materials(asset_dir / "asset.yaml")
    mats = {}
    for name, m in asset.materials.items():
        src = raw.get(name) or {}
        explicit = sorted(k for k in src if k not in ("archetype", "use", "doc", "layers"))
        mats[name] = {"archetype": m.get("archetype"), "instance_of": m.get("instance_of"), "explicit_params": explicit,
                      "layers": len(m.get("layers") or []), "textured": m.get("textured")}
    images = sorted(str(p.relative_to(asset_dir)) for p in asset_dir.rglob("*")
                    if p.suffix.lower() in IMAGE_EXT and ".build" not in p.parts and "export" not in p.parts
                    and "history" not in p.parts)
    return {
        "asset": asset.name,
        "triangles": sum(len(p.mesh.F) for p in asset.parts),
        "materials": mats,
        "escape": {"image_files": images, "image_layers": sum(m["layers"] for m in mats.values()),
                   "flat_materials": [n for n, m in mats.items() if m["archetype"] == "flat" and not m["textured"]]},
        "bake": None if tex is None else {"resolution": tex.resolution, "needed": tex.needed_resolution,
                                          "target_px_m": tex.target_px_m, "achieved_px_m": round(tex.achieved_px_m, 1),
                                          "lifecycle": sorted(set(tex.lifecycle.values()))},
        "surface_issues": sorted({i["code"] for i in report["issues"] if i["code"].startswith(("TEX_", "PBR_", "UV_"))}),
        "material_edits": material_edits(asset_dir),
    }


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    res = analyze(Path(argv[0]).resolve())
    if "--json" in argv:
        print(json.dumps(res, indent=1))
        return 0
    print(f"{res['asset']}: {res['triangles']} tris, bake {res['bake']}")
    for n, m in res["materials"].items():
        print(f"  {n:14s} {m['archetype']:8s} use={m['instance_of']} layers={m['layers']} params={m['explicit_params']}")
    print(f"escape: {res['escape']}")
    print(f"surface issues: {res['surface_issues']}")
    for e in res["material_edits"]:
        print(f"  {e['from']} -> {e['to']}: {len(e['changes'])} material edits  {e['changes'][:8]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
