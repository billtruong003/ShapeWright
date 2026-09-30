"""Pack-level inspection: several assets judged as one set.

`sw pack` builds a group of assets (named, or selected by `asset.tags`), renders
them side by side **at one common scale** (same metres-per-pixel in every tile,
shared ground line) and reports what makes a set coherent or not:

- materials: one name must mean one definition across the pack;
- shared params: the same name with different values is usually drift;
- detail density: triangles per square metre of surface, per asset;
- texel density: px/m of each asset's own atlas (one texture per asset);
- per-asset validation status and budgets.

Findings are informational (a pack may deliberately differ); the sheet is for
looking, the numbers are for arguing about what you see.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import paths
from .assemble import Asset, build, resolve_asset_path
from .render.views import _font, render
from .surface import build_surface
from .validate.run import run_validation

PACK_ROWS = [("front", "clay"), ("front_right", "material"), ("front_right", "silhouette")]


def select(refs: list[str], tag: str | None, base: Path | None = None, pack: str | None = None) -> list[Path]:
    paths = [resolve_asset_path(r) for r in refs]
    if pack:
        from .source import read_yaml

        for p in sorted((base or paths.assets_home()).glob("*/asset.yaml")):
            ref = str(read_yaml(p).get("pack", ""))
            if ref and (ref == pack or Path(ref).stem == pack) and p.resolve() not in [q.resolve() for q in paths]:
                paths.append(p)
    if tag:
        for p in sorted((base or paths.assets_home()).glob("*/asset.yaml")):
            try:
                a = build(p)
            except Exception:  # broken assets are reported by `sw bench`, not here
                continue
            if tag in ((a.meta or {}).get("tags") or []) and p.resolve() not in [q.resolve() for q in paths]:
                paths.append(p)
    return paths


def _surface_area(asset: Asset) -> float:
    return float(sum(p.mesh.area() for p in asset.parts))


def pack_report(assets: list[Asset], reports: list[dict]) -> dict:
    rows = []
    for a, r in zip(assets, reports):
        m = r["metrics"]
        size = (a.bounds()[1] - a.bounds()[0]).round(3).tolist()
        area = _surface_area(a)
        rows.append({"asset": a.name, "status": r["status"], "triangles": a.n_tris, "budget": a.budget.get("triangles"),
                     "size_m": size, "materials": sorted(a.materials), "parts": len(a.parts),
                     "tris_per_m2": round(a.n_tris / max(area, 1e-9), 1),
                     "texel_px_m": m.get("texel_density_px_m"),
                     "errors": [i["code"] for i in r["issues"] if i["severity"] == "error"],
                     "warnings": [i["code"] for i in r["issues"] if i["severity"] == "warning"]})
    findings = []
    # one material name = one definition
    defs: dict[str, dict[str, list[str]]] = {}
    for a in assets:
        for name, mat in a.materials.items():
            key = repr(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in mat.items() if k != "doc"))
            defs.setdefault(name, {}).setdefault(key, []).append(a.name)
    for name, variants in sorted(defs.items()):
        if len(variants) > 1:
            findings.append({"code": "PACK_MATERIAL_DRIFT", "detail": f"material '{name}' has {len(variants)} different definitions: "
                             + " | ".join(", ".join(v) for v in variants.values())})
    used = {n for a in assets for n in a.materials}
    for name in sorted(used):
        users = [a.name for a in assets if name in a.materials]
        if len(users) == 1 and len(assets) > 1:
            findings.append({"code": "PACK_MATERIAL_UNIQUE", "detail": f"material '{name}' is used only by {users[0]}"})
    # same param name, different value
    values: dict[str, dict[float, list[str]]] = {}
    for a in assets:
        for k, v in a.env.items():
            values.setdefault(k, {}).setdefault(round(float(v), 6), []).append(a.name)
    for k, vs in sorted(values.items()):
        owners = sum(len(x) for x in vs.values())
        if owners > 1 and len(vs) > 1:
            findings.append({"code": "PACK_PARAM_DIFFERS", "detail": f"param '{k}': " + "; ".join(f"{v:g} in {', '.join(n)}" for v, n in vs.items())})
    for key, label, limit in (("tris_per_m2", "detail density (tris/m2 of surface)", 3.0), ("texel_px_m", "texel density (px/m, own atlas)", 2.0)):
        vals = [(r[key], r["asset"]) for r in rows if r[key]]
        if len(vals) > 1:
            lo, hi = min(vals), max(vals)
            spread = hi[0] / max(lo[0], 1e-9)
            findings.append({"code": "PACK_DENSITY_SPREAD" if spread > limit else "PACK_DENSITY",
                             "detail": f"{label}: {spread:.2f}x spread ({lo[1]} {lo[0]:g} .. {hi[1]} {hi[0]:g}); flagged above {limit:g}x"})
    return {"assets": rows, "findings": findings}


def common_frame(assets: list[Asset]) -> np.ndarray:
    """Half-extents shared by every tile, so all tiles have the same metres per pixel."""
    ext = np.max([a.bounds()[1] - a.bounds()[0] for a in assets], 0)
    top = max(float(a.bounds()[1][1]) for a in assets)
    bottom = min(float(a.bounds()[0][1]) for a in assets)
    return np.array([ext[0], top - min(bottom, 0.0), ext[2]])


def pack_sheet(assets: list[Asset], surfaces: list, tile: int = 300, rows=None) -> Image.Image:
    rows = rows or PACK_ROWS
    ext = common_frame(assets)
    sheet = Image.new("RGB", (tile * len(assets), tile * len(rows) + 22), (255, 255, 255))
    for i, (a, s) in enumerate(zip(assets, surfaces)):
        b = a.bounds()
        c = (b[0] + b[1]) / 2
        # same box for everyone, centred on this asset, floor at y = 0 (wall/free props hang in the same frame)
        frame = np.array([[c[0] - ext[0] / 2, 0.0, c[2] - ext[2] / 2], [c[0] + ext[0] / 2, ext[1], c[2] + ext[2] / 2]])
        for j, (view, mode) in enumerate(rows):
            label = f"{a.name} | {a.n_tris} tris" if j == 0 else f"{view} | {mode}"
            im = render(a, s, view, mode, tile, frame=frame, label=label)
            sheet.paste(im, (i * tile, j * tile))
    d = ImageDraw.Draw(sheet)
    for i in range(1, len(assets)):
        d.line([(i * tile, 0), (i * tile, len(rows) * tile)], fill=(255, 255, 255), width=2)
    d.text((6, len(rows) * tile + 4), "common scale: every tile shows the same metres per pixel (same box, centred on each asset, floor at y=0)",
           fill=(40, 40, 40), font=_font(12))
    return sheet


def run_pack(paths: list[Path], tile: int = 300):
    assets = [build(p) for p in paths]
    surfaces = [build_surface(a) for a in assets]
    reports = [run_validation(a, s) for a, s in zip(assets, surfaces)]
    return assets, surfaces, reports, pack_report(assets, reports)


def format_pack(rep: dict) -> str:
    out = [f"{'asset':24} {'status':6} {'tris':>10} {'size x y z (m)':20} {'tris/m2':>8} {'px/m':>6}  materials"]
    for r in rep["assets"]:
        budget = f"/{r['budget']}" if r["budget"] else ""
        sz = " ".join(f"{v:.2f}" for v in r["size_m"])
        out.append(f"{r['asset']:24} {r['status']:6} {str(r['triangles']) + budget:>10} {sz:20} {r['tris_per_m2']:8g} {r['texel_px_m'] or 0:6g}  "
                   f"{', '.join(r['materials'])}  {' '.join(r['errors'] + r['warnings'])}")
    out.append("")
    out.extend(f"  {f['code']}: {f['detail']}" for f in rep["findings"]) if rep["findings"] else out.append("  no pack findings")
    return "\n".join(out)


def sheet_path(name: str) -> Path:
    d = paths.build_dir() / "packs"
    d.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name) or "pack"
    return d / f"{safe}.png"


__all__ = ["select", "pack_report", "pack_sheet", "run_pack", "format_pack", "sheet_path", "common_frame"]
