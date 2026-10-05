"""LOD files (docs/PRODUCTION.md): decimated copies that keep LOD0's UVs and atlas, with a
silhouette check against LOD0. Engines assemble LOD groups from the files; Godot builds its own
LODs at import, so the godot target writes none."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np

from .. import backend
from ..assemble import Asset
from ..surface import Surface, build_surface

VIEWS = ("front", "right", "top", "front_right")


def lod_asset(asset: Asset, surface: Surface, ratio: float) -> tuple[Asset, Surface]:
    parts, uvs = [], {}
    for p in asset.parts:
        m = p.mesh.copy()
        cu = surface.parts[p.name].corner_uv
        if cu is not None:
            m.cattr["uv"] = cu.astype(np.float64)  # decimation transfers these (Phase 11), so LOD0's atlas still fits
            m.invalidated.discard("uv")
        d = backend.simplify(m, ratio).merged() if m.n_tris > 16 else m
        parts.append(dataclasses.replace(p, mesh=d))
        if "uv" in d.cattr:
            uvs[p.name] = d.cattr["uv"]
    lod = dataclasses.replace(asset, parts=parts)
    return lod, build_surface(lod, uvs)


def silhouette_iou(a0: Asset, s0: Surface, a1: Asset, s1: Surface, size: int = 200) -> float:
    from ..history import _mask

    frame = a0.bounds()
    ious = []
    for v in VIEWS:
        m0, m1 = _mask(a0, s0, v, frame, size), _mask(a1, s1, v, frame, size)
        ious.append((m0 & m1).sum() / max((m0 | m1).sum(), 1))
    return float(min(ious))


def write_lods(asset: Asset, surface: Surface, out: Path, ratios, status: str = "UNKNOWN", proxies=None) -> list[dict]:
    from ..bake import textures_for
    from .gltf import collision_proxies, write_glb

    tex = textures_for(asset, surface)
    if proxies is None:
        proxies = collision_proxies(asset)  # LOD0's collision in every LOD file
    report = []
    for n, r in enumerate(ratios, start=1):
        a, s = lod_asset(asset, surface, float(r))
        path = out.with_name(f"{out.stem}_LOD{n}.glb")
        info = write_glb(a, s, path, status, textures=tex, collision=proxies)
        iou = silhouette_iou(asset, surface, a, s)
        report.append({"lod": n, "ratio": float(r), "path": str(path), "triangles": a.n_tris, "silhouette_iou": round(iou, 3),
                       "bytes": info["bytes"]})
    return report
