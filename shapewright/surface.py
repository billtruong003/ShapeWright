"""Surface stage: per-corner normals and UVs, then export-ready vertex buffers.

Geometry stays welded (indexed) through modelling. Here each part is expanded
to face corners, given a normal (flat / smooth / auto-smooth by angle) and a
UV from a single asset-wide atlas (xatlas), then re-deduplicated into the
vertex buffers that the renderer and glTF exporter share. Sharing one surface
result between renderer and exporter means what the agent inspects is what
ships.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .assemble import Asset, Part
from .mesh import Mesh


@dataclass
class SurfacePart:
    name: str
    positions: np.ndarray  # (k, 3) float32
    normals: np.ndarray  # (k, 3) float32
    uvs: np.ndarray | None  # (k, 2) float32, or None
    indices: np.ndarray  # (m, 3) uint32
    corner_uv: np.ndarray | None  # (m, 3, 2) for validation


@dataclass
class Surface:
    parts: dict[str, SurfacePart]
    uv_method: str
    uv_resolution: int
    uv_padding: int
    uv_error: str = ""


def corner_normals(mesh: Mesh, mode: str, angle_deg: float) -> np.ndarray:
    fn, area = mesh.face_normals()
    m = len(mesh.F)
    if mode == "flat":
        return np.repeat(fn[:, None, :], 3, axis=1)
    out = np.zeros((m, 3, 3))
    cos_lim = -2.0 if mode == "smooth" else np.cos(np.radians(angle_deg))
    flat_idx = mesh.F.reshape(-1)
    order = np.argsort(flat_idx, kind="stable")
    sorted_v = flat_idx[order]
    bounds = np.flatnonzero(np.diff(sorted_v)) + 1
    for group in np.split(order, bounds):
        faces = group // 3
        corners = group % 3
        N = fn[faces]
        mask = (N @ N.T) >= cos_lim
        acc = (mask * area[faces][None, :]) @ N
        length = np.linalg.norm(acc, axis=1)
        acc = np.where(length[:, None] > 1e-12, acc / np.maximum(length, 1e-12)[:, None], N)
        out[faces, corners] = acc
    return out


def _unwrap(parts: list[Part], resolution: int, padding: int) -> list[np.ndarray]:
    """Return per-part (m, 3, 2) corner UVs from one shared xatlas atlas."""
    import xatlas

    V = np.concatenate([p.mesh.V for p in parts]).astype(np.float32)
    offsets = np.cumsum([0] + [len(p.mesh.V) for p in parts])
    F = np.concatenate([p.mesh.F + o for p, o in zip(parts, offsets)]).astype(np.uint32)
    atlas = xatlas.Atlas()
    atlas.add_mesh(V, F)
    chart = xatlas.ChartOptions()
    pack = xatlas.PackOptions()
    pack.resolution = resolution
    pack.padding = padding
    pack.bilinear = True
    pack.rotate_charts = True
    atlas.generate(chart, pack)
    vmap, idx, uvs = atlas[0]
    corner = uvs[idx]  # xatlas preserves face order
    out, start = [], 0
    for p in parts:
        out.append(corner[start:start + p.mesh.n_tris].astype(np.float64))
        start += p.mesh.n_tris
    return out


def build_surface(asset: Asset) -> Surface:
    uv_cfg = asset.uv or {}
    method = uv_cfg.get("method", "auto")
    resolution = int(uv_cfg.get("resolution", asset.budget.get("texture_size", 1024)))
    padding = int(uv_cfg.get("padding_px", (asset.profile.get("uv") or {}).get("padding_px", 4)))
    corner_uvs: list = [None] * len(asset.parts)
    err = ""
    if method == "auto":
        try:
            corner_uvs = _unwrap(asset.parts, resolution, padding)
        except Exception as e:  # missing binary wheel or atlas failure
            err = str(e)
            method = "none"
    out = {}
    for p, cuv in zip(asset.parts, corner_uvs):
        pos = p.mesh.V[p.mesh.F]  # (m,3,3)
        nrm = corner_normals(p.mesh, p.shading, p.smooth_angle)
        cols = [pos.reshape(-1, 3), nrm.reshape(-1, 3)]
        if cuv is not None:
            cols.append(cuv.reshape(-1, 2))
        key = np.round(np.concatenate(cols, axis=1), 6)
        uniq, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
        # stable vertex order: order of first appearance
        rank = np.empty(len(first), dtype=np.int64)
        rank[np.argsort(first, kind="stable")] = np.arange(len(first))
        sel = np.sort(first)
        out[p.name] = SurfacePart(
            p.name,
            cols[0][sel].astype(np.float32),
            cols[1][sel].astype(np.float32),
            cols[2][sel].astype(np.float32) if cuv is not None else None,
            rank[inverse.reshape(-1)].reshape(-1, 3).astype(np.uint32),
            cuv,
        )
    return Surface(out, method, resolution, padding, err)
