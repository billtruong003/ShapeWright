"""Material preview sheet: each material of an asset on the same reference shapes and lights."""

from __future__ import annotations

import copy

import yaml
from PIL import Image

from .assemble import Asset, build
from .render.views import render
from .surface import build_surface


def material_sheet(asset: Asset, tile: int = 256):
    names = list(asset.materials)
    src = copy.deepcopy({k: v for k, v in asset.source.items() if not k.startswith("_")})
    src.pop("pack", None)  # materials are already merged into the source
    src.pop("extends", None)
    src.pop("interface", None)
    src.pop("checks", None)
    src.pop("sockets", None)
    parts = {}
    for i, n in enumerate(names):
        x = i * 0.8
        parts[f"m{i}_box"] = {"shape": {"type": "chamfer_box", "size": [0.4, 0.3, 0.3], "chamfer": 0.03}, "anchor": "bottom",
                              "position": [x, 0, 0.2], "material": n}
        parts[f"m{i}_ball"] = {"shape": {"type": "sphere", "radius": 0.17, "segments": 24, "rings": 12}, "anchor": "bottom",
                               "position": [x, 0, -0.25], "material": n, "shading": "smooth"}
    src["parts"] = parts
    src["uv"] = {**(src.get("uv") or {}), "method": "regions"}
    tmp = asset.dir / ".materials_preview.yaml"
    tmp.write_text(yaml.safe_dump(src, sort_keys=False))
    try:
        a = build(tmp)
        s = build_surface(a)
    finally:
        tmp.unlink(missing_ok=True)
    sheet = Image.new("RGB", (tile * len(names), tile * 2), (255, 255, 255))
    notes = []
    for i, n in enumerate(names):
        frame = None
        sub = [p for p in a.parts if p.material == n]
        import numpy as np

        frame = np.stack([np.min([p.bounds[0] for p in sub], 0), np.max([p.bounds[1] for p in sub], 0)])
        m = asset.materials[n]
        label = f"{n} ({m['archetype']}{', use ' + m['instance_of'] if m.get('instance_of') else ''})"
        iso = [f"m{i}_box", f"m{i}_ball"]
        sheet.paste(render(a, s, "front_right", "textured", tile, focus=iso, isolate=True, frame=frame, label=label), (i * tile, 0))
        sheet.paste(render(a, s, "front_right", "albedo", tile, focus=iso, isolate=True, frame=frame, label="albedo"), (i * tile, tile))
        def fmt(v):
            if isinstance(v, list):
                return "#" + "".join(f"{int(round(x * 255)):02x}" for x in v[:3])
            return f"{v:g}" if isinstance(v, float) else str(v)
        notes.append(f"{n:16} archetype {m['archetype']:8} " + " ".join(f"{k}={fmt(v)}" for k, v in m["args"].items()
                                                                        if k not in ("seed",) and v not in (None, 0, 0.0)))
    return sheet, notes
