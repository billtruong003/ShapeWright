"""Regenerate the README and site presentation images with the beauty renderer (deterministic).

Usage: python tools/site/readme_images.py   -> docs/images/readme_houses.png, readme_gallery.png, readme_turntable.gif
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

HOUSES = ["house_cottage", "house_townhouse", "house_workshop"]
PROPS = ["tavern_chair", "treasure_chest", "ornate_fountain", "well_winch", "iron_lantern", "rope_bridge", "battle_axe", "mine_cart"]


def main():
    from PIL import Image

    from shapewright.assemble import build
    from shapewright.render.beauty import render_beauty, save_turntable, turntable
    from shapewright.surface import build_surface

    out = ROOT / "docs" / "images"
    tile = 600
    sheet = Image.new("RGB", (tile * len(HOUSES), tile))
    for i, name in enumerate(HOUSES):
        a = build(ROOT / "assets" / name)
        sheet.paste(render_beauty(a, build_surface(a), "front_right", tile), (i * tile, 0))
    sheet.save(out / "readme_houses.png")
    tile = 360
    sheet = Image.new("RGB", (tile * 4, tile * 2))
    for i, name in enumerate(PROPS):
        a = build(ROOT / "assets" / name)
        sheet.paste(render_beauty(a, build_surface(a), "front_right", tile), ((i % 4) * tile, (i // 4) * tile))
    sheet.save(out / "readme_gallery.png")
    a = build(ROOT / "assets" / "treasure_chest")
    save_turntable(turntable(a, build_surface(a), 24, 320), out / "readme_turntable.gif")
    print("wrote", ", ".join(str(p.relative_to(ROOT)) for p in sorted(out.glob("readme_*"))))


if __name__ == "__main__":
    main()
