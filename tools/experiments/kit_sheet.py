"""Contact sheet of several assets rendered the same way (modular kit review, MODULAR_HOUSE_PACK_01).

Usage: python tools/experiments/kit_sheet.py OUT.png [--view front_right] [--mode textured] [--size 360] ASSET...
Each asset is rendered with `sw render` settings (same camera logic, each asset framed on its own) and
labelled; the tiles are laid out in rows of four.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main(argv):
    from PIL import Image

    from shapewright.assemble import build, resolve_asset_path
    from shapewright.render.views import render
    from shapewright.surface import build_surface

    out = Path(argv[0])
    opts = {"--view": "front_right", "--mode": "textured", "--size": "360"}
    names, i = [], 1
    while i < len(argv):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]
            i += 2
        else:
            names.append(argv[i])
            i += 1
    size = int(opts["--size"])
    tiles = []
    for n in names:
        a = build(resolve_asset_path(n))
        tiles.append(render(a, build_surface(a), opts["--view"], opts["--mode"], size))
    cols = min(4, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * size, rows * size), (235, 233, 228))
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % cols) * size, (k // cols) * size))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1:])
