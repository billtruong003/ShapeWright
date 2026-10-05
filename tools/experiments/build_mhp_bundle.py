"""Assemble the downloadable MODULAR_HOUSE_PACK_01 deliverable from the repository.

Usage: python tools/experiments/build_mhp_bundle.py [OUT_DIR]   (default: modular_house_pack/)

Run `sw export` for every house_* asset first (and `sw export house_X --target godot` for the demo houses).
Copies sources, writes the shared material table, dumps each asset's baked atlas (base colour + ORM),
collects GLBs, renders a contact sheet per group and a hero render per house, copies validation reports
and seam-probe results, and writes metrics.json.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "experiments"))

HOUSES = ["house_cottage", "house_townhouse", "house_workshop"]
GROUPS = {
    "walls": ["house_wall_plain", "house_wall_window", "house_wall_window_offset", "house_wall_door", "house_wall_shopfront",
              "house_wall_half", "house_wall_upper"],
    "framing": ["house_corner", "house_post", "house_beam_vertical", "house_beam", "house_brace"],
    "floors_foundation": ["house_floor", "house_floor_half", "house_footing", "house_steps"],
    "roof": ["house_roof_section", "house_roof_end", "house_gable", "house_ridge", "house_roof_eave", "house_chimney"],
    "openings": ["house_window", "house_door_frame", "house_door", "house_shutter"],
}


def main(out: Path):
    from PIL import Image

    from shapewright.assemble import build
    from shapewright.bake import textures_for
    from shapewright.preview import material_sheet
    from shapewright.render.views import render
    from shapewright.surface import build_surface

    if out.exists():
        shutil.rmtree(out)
    for d in ("sources/packs", "sources/styles", "sources/components", "sources/assets", "materials", "textures", "modules",
              "demo_houses", "renders", "validation"):
        (out / d).mkdir(parents=True, exist_ok=True)
    assets = sorted(p.parent.name for p in (ROOT / "assets").glob("house_*/asset.yaml"))

    # ---- sources
    shutil.copy(ROOT / "packs" / "cozy_house.yaml", out / "sources" / "packs")
    shutil.copy(ROOT / "styles" / "cozy_timber.yaml", out / "sources" / "styles")
    for c in sorted((ROOT / "components").glob("house_*.yaml")) + [ROOT / "components" / "plank_top.yaml"]:
        shutil.copy(c, out / "sources" / "components")
    for a in assets:
        d = out / "sources" / "assets" / a
        d.mkdir(parents=True, exist_ok=True)
        for f in ("asset.yaml", "uv.lock.yaml"):
            if (ROOT / "assets" / a / f).exists():
                shutil.copy(ROOT / "assets" / a / f, d / f)

    # ---- materials: the shared table + a material sheet
    pack = yaml.safe_load((ROOT / "packs" / "cozy_house.yaml").read_text())
    (out / "materials" / "materials.yaml").write_text(
        "# The cozy_house pack's shared materials (read-only in every module and house).\n" + yaml.safe_dump(pack["materials"], sort_keys=False))
    cottage = build(ROOT / "assets" / "house_cottage")
    img, _ = material_sheet(cottage, tile=256)
    img.save(out / "materials" / "material_sheet.png")

    # ---- per asset: textures, GLB, report, hero render
    for a in assets:
        asset = build(ROOT / "assets" / a)
        surf = build_surface(asset)
        tex = textures_for(asset, surf)
        if tex is not None:
            Image.fromarray((np.clip(tex.base, 0, 1) * 255).astype(np.uint8)).save(out / "textures" / f"{a}_basecolor.png")
            Image.fromarray((np.clip(tex.orm, 0, 1) * 255).astype(np.uint8)).save(out / "textures" / f"{a}_orm.png")
        dest = out / ("demo_houses" if a in HOUSES else "modules")
        for g in sorted((ROOT / "assets" / a / "export").glob("*.glb")):
            if "_LOD" not in g.name:
                shutil.copy(g, dest / g.name)
        rep = ROOT / "assets" / a / "export" / f"{a}.report.json"
        if rep.exists():
            shutil.copy(rep, out / "validation" / rep.name)
        if a in HOUSES:
            for v in ("front_right", "back_left", "front"):
                render(asset, surf, v, "textured", 900).save(out / "renders" / f"{a}_{v}.png")
                render(asset, surf, v, "beauty", 900).save(out / "renders" / f"{a}_{v}_beauty.png")

    # ---- contact sheets per module group
    for g, names in GROUPS.items():
        tiles = []
        for n in names:
            asset = build(ROOT / "assets" / n)
            tiles.append(render(asset, build_surface(asset), "front_right", "textured", 360))
        cols = 4
        sheet = Image.new("RGB", (cols * 360, ((len(tiles) + cols - 1) // cols) * 360), (235, 233, 228))
        for k, t in enumerate(tiles):
            sheet.paste(t, ((k % cols) * 360, (k // cols) * 360))
        sheet.save(out / "renders" / f"modules_{g}.png")

    # ---- seam diagnostics and evidence
    ev = ROOT / "docs" / "experiments" / "mhp01" / "evidence"
    for f in sorted(ev.glob("*")):
        shutil.copy(f, (out / "validation" if f.suffix in (".json", ".txt") else out / "renders") / f.name)

    # ---- metrics
    from mhp_metrics import main as metrics_main
    metrics_main(out / "metrics.json")
    shutil.copy(out / "metrics.json", ROOT / "docs" / "experiments" / "mhp01" / "metrics.json")
    print(f"bundle written to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "modular_house_pack")
