"""Pack trim sheet (Phase 21): one shared texture for every member of a pack.

A pack that declares `atlas: {size: 2048, density: 128}` gets one trim sheet: each pack material owns a
horizontal strip of the texture (full width, `size / n` pixels tall). Members do not get an atlas of their own;
their faces are mapped onto their material's strip:

* faces are grouped per part by plane (rounded normal); each group is projected onto its own plane, so there is
  no stretching on slopes;
* U runs along the part's long axis projected on that plane (wood grain follows the timber) at `density` px/m,
  offset per group so neighbouring copies do not show the same grain, and kept inside one texture width when the
  group fits (no seam where the texture wraps);
* V spans the strip. A group taller than the strip is scaled to fit it (lower density on that face, reported).

The strip content is the material recipe evaluated on a flat patch in strip space (metres), so it is the same
for every member: the texture is identical bytes in every module and engines can share one copy.
Edge wear and grime that depend on a part's own edges are not part of a trim sheet (they need a per-asset bake).
"""

from __future__ import annotations

import hashlib
import json
import zlib

import numpy as np

PAD_PX = 6  # rows kept free at the top and bottom of each strip (filtering, mips)
_CACHE: dict = {}


def config(asset) -> dict | None:
    """The pack's trim-sheet settings for this asset, or None (no pack atlas, or the asset opted out)."""
    cfg = (asset.source or {}).get("_pack_atlas")
    if not cfg or (asset.uv or {}).get("method") not in (None, "trim"):
        return None
    size = int(cfg.get("size", 2048))
    names = list(cfg.get("materials") or asset.source.get("_pack_materials") or asset.materials)
    return {"size": size, "density": float(cfg.get("density", size / 16)), "materials": names,
            "pack": str(asset.source.get("_pack") or "pack")}


def strip_of(cfg: dict, material: str | None) -> int:
    names = cfg["materials"]
    return names.index(material) if material in names else 0


def _basis(n: np.ndarray, axis: np.ndarray):
    t1 = axis - n * float(axis @ n)
    if np.linalg.norm(t1) < 1e-3:  # the long axis is the normal: use world up, then x
        for alt in (np.array([0.0, 1.0, 0.0]), np.array([1.0, 0.0, 0.0])):
            t1 = alt - n * float(alt @ n)
            if np.linalg.norm(t1) > 1e-3:
                break
    t1 /= np.linalg.norm(t1)
    return t1, np.cross(n, t1)


def corner_uvs(part, cfg: dict) -> tuple[np.ndarray, float]:
    """(m,3,2) corner UVs on the trim sheet for one part, and the lowest density used (px/m)."""
    from .bake import _principal_axis

    mesh = part.mesh
    V, F = mesh.V, mesh.F
    fn, _ = mesh.face_normals()
    R, D = cfg["size"], cfg["density"]
    n_strips = max(len(cfg["materials"]), 1)
    strip_px = R / n_strips
    usable = strip_px - 2 * PAD_PX
    axis = _principal_axis(V)
    mats = np.array([m if m else part.material for m in mesh.label_values("material")], dtype=object)
    out = np.zeros((len(F), 3, 2))
    worst = D
    keys = np.round(fn * 20).astype(np.int64)
    groups: dict = {}
    for f in range(len(F)):
        groups.setdefault((tuple(keys[f]), mats[f]), []).append(f)
    for gi, ((_, mat), faces) in enumerate(sorted(groups.items(), key=lambda kv: (kv[1][0]))):
        faces = np.asarray(faces)
        n = fn[faces].mean(0)
        n /= max(np.linalg.norm(n), 1e-12)
        t1, t2 = _basis(n, axis)
        P = V[F[faces]]  # (k,3,3)
        u = P @ t1
        v = P @ t2
        ulo, uhi, vlo, vhi = u.min(), u.max(), v.min(), v.max()
        scale = 1.0
        if (vhi - vlo) * D > usable:
            scale = usable / max((vhi - vlo) * D, 1e-9)
            worst = min(worst, D * scale)
        span_u = (uhi - ulo) * D * scale / R  # in texture widths
        seed = zlib.crc32(f"{part.base}:{gi}".encode()) / 2**32
        u0 = seed * max(0.0, 1.0 - span_u)  # stay inside one texture width when the group fits
        k = strip_of(cfg, mat)
        out[faces, :, 0] = u0 + (u - ulo) * D * scale / R
        out[faces, :, 1] = (k * strip_px + PAD_PX + (v - vlo) * D * scale) / R
    return out, worst


def _key(asset, cfg) -> str:
    mats = {m: asset.materials.get(m) for m in cfg["materials"]}
    blob = json.dumps({"cfg": cfg, "mats": mats}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def bake(asset, cfg: dict):
    """The pack's trim sheet as bake.Textures (cached: every member of the pack gets the same object)."""
    from . import bake as B

    key = _key(asset, cfg)
    if key in _CACHE:
        return _CACHE[key]
    R, D = cfg["size"], cfg["density"]
    names = cfg["materials"]
    n_strips = max(len(names), 1)
    strip_px = R / n_strips
    base = np.zeros((R, R, 3))
    orm = np.zeros((R, R, 3))
    orm[..., 0] = 1.0
    tex = B.Textures(R, None, None, None, None, D, D, R)
    images: dict = {}
    xs = (np.arange(R) + 0.5) / D  # metres along the strip
    for k, name in enumerate(names):
        mat = asset.materials.get(name)
        r0, r1 = int(round(k * strip_px)), int(round((k + 1) * strip_px))
        rows = np.arange(r0, r1)
        if mat is None or not len(rows):
            continue
        # `rows` count texel rows from the bottom (v = (row + 0.5) / R); metres up the strip from its padded bottom edge
        vm = ((rows + 0.5) - k * strip_px - PAD_PX) / D
        X, Y = np.meshgrid(xs, vm)
        P = np.stack([X.ravel(), Y.ravel(), np.zeros(X.size)], 1)
        N = np.tile([0.0, 0.0, 1.0], (len(P), 1))
        far = np.full(len(P), np.inf)
        _, ch, col = B.evaluate_material(asset, name, mat, P, N, far, far, Y.ravel() + 1.0, np.array([1.0, 0.0, 0.0]),
                                         np.zeros(3), 0, images, tex)
        img_rows = R - 1 - rows  # image row index (top = v 1)
        base[img_rows] = np.clip(col, 0, 1).reshape(len(rows), R, 3)
        orm[img_rows, :, 1] = np.clip(ch.roughness, 0, 1).reshape(len(rows), R)
        orm[img_rows, :, 2] = np.clip(ch.metallic, 0, 1).reshape(len(rows), R)
    tex.base, tex.orm = base, orm
    tex.covered = np.ones((R, R), dtype=bool)
    edge = np.zeros((R, R), dtype=bool)
    for k in range(1, n_strips):
        edge[R - 1 - int(round(k * strip_px))] = True
    tex.seams = edge
    tex.lifecycle = {p.name: "DERIVED" for p in asset.parts}
    tex.trim = {"pack": cfg["pack"], "key": key, "strips": names}
    _CACHE[key] = tex
    return tex
