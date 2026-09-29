"""Close-up render of a region of an assembled asset (modular seam review, MODULAR_HOUSE_PACK_01).

Usage: python tools/experiments/closeup.py ASSET OUT.png VIEW MODE xmin ymin zmin xmax ymax zmax [--size 640]
Frames the camera on the given world box (only framing: every part is still drawn), so joints between
modules can be inspected at a readable scale.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main(argv):
    from shapewright.assemble import build, resolve_asset_path
    from shapewright.render.views import render
    from shapewright.surface import build_surface

    size = int(argv[argv.index("--size") + 1]) if "--size" in argv else 640
    args = [a for i, a in enumerate(argv) if a != "--size" and (i == 0 or argv[i - 1] != "--size")]
    asset, out, view, mode = args[0], Path(args[1]), args[2], args[3]
    box = np.array([float(v) for v in args[4:10]]).reshape(2, 3)
    a = build(resolve_asset_path(asset))
    img = render(a, build_surface(a), view, mode, size, frame=box, label=f"{asset} | {view} | {mode} | close-up")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1:])
