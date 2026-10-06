"""Toon showcase of finished assets (Phase 25b): cel shading with continuous post-process outlines (CPU, deterministic).

Usage: python tools/site/toon_showcase.py   -> docs/images/toon_showcase.png (+ website/assets/toon_showcase.png)
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SHOWCASE = [  # what the framework is good at: low-poly props, kits and stylised creatures
    "house_bakery", "house_workshop", "house_cottage", "ornate_fountain",
    "treasure_chest", "mine_cart", "well_winch", "street_lamp",
    "chibi_fox", "creature_slime", "creature_mushroom", "wheelbarrow",
]


def main(tile: int = 420):
    from PIL import Image

    from shapewright.assemble import build
    from shapewright.render.views import render
    from shapewright.surface import build_surface

    cols = 4
    rows = (len(SHOWCASE) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile, rows * tile), (236, 235, 231))
    for i, name in enumerate(SHOWCASE):
        a = build(ROOT / "assets" / name)
        im = render(a, build_surface(a), "front_right", "toon", tile, label=name.replace("_", " "))
        sheet.paste(im, ((i % cols) * tile, (i // cols) * tile))
        print(name, flush=True)
    out = ROOT / "docs" / "images" / "toon_showcase.png"
    sheet.quantize(192).save(out, optimize=True)
    shutil.copy(out, ROOT / "website" / "assets" / "toon_showcase.png")
    print("wrote", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
