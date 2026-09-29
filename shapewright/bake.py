"""Bake stage: evaluate material recipes at 3D surface points into the UV atlas.

For every atlas texel covered by a face, the texel's 3D position, normal and
distance to sharp convex edges are reconstructed from barycentric coordinates.
The face's material recipe is evaluated there (object space). The result is
two textures shared by all materials of the asset: base colour (sRGB) and ORM
(glTF metallicRoughness: G = roughness, B = metallic; R = occlusion, 1 today).

Because evaluation happens in object space, textures are regenerated
consistently after any UV change (lifecycle state DERIVED, docs/SURFACES.md).
Resolution follows the texel-density target, so a pack gets consistent px/m.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import materials as M
from .assemble import Asset
from .limits import LIMITS
from .surface import Surface

IMAGE_TYPES = {".png", ".jpg", ".jpeg"}


@dataclass
class Textures:
    resolution: int
    base: np.ndarray  # (r, r, 3) sRGB 0..1
    orm: np.ndarray  # (r, r, 3) occlusion, roughness, metallic
    covered: np.ndarray  # (r, r) bool, before dilation
    seams: np.ndarray  # (r, r) bool: chart borders
    target_px_m: float
    achieved_px_m: float
    needed_resolution: int
    lifecycle: dict = field(default_factory=dict)  # part -> DERIVED | VALID | REGION_KEPT | RELAYOUT | INVALID
    material_stats: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)  # (code, severity, message, where, hint)


def needs_textures(asset: Asset) -> bool:
    return any(m.get("textured") for m in asset.materials.values())


# ------------------------------------------------------------------ geometry helpers


def _sharp_edges(mesh, angle_deg: float = 25.0):
    """Per face, per corner k: (edge opposite corner k is sharp & convex, ... sharp & concave, altitude from k)."""
    F, V = mesh.F, mesh.V
    fn, _ = mesh.face_normals()
    m = len(F)
    sharp = np.zeros((m, 3), dtype=bool)
    crease = np.zeros((m, 3), dtype=bool)
    edge_map: dict = {}
    for f in range(m):
        for k in range(3):
            a, b = F[f, (k + 1) % 3], F[f, (k + 2) % 3]
            edge_map.setdefault((min(a, b), max(a, b)), []).append((f, k))
    cos_lim = np.cos(np.radians(angle_deg))
    for users in edge_map.values():
        if len(users) != 2:
            for f, k in users:
                sharp[f, k] = True  # boundary
            continue
        (f1, k1), (f2, k2) = users
        if fn[f1] @ fn[f2] > cos_lim:
            continue
        c2 = V[F[f2]].mean(0) - V[F[f1]].mean(0)
        if fn[f1] @ c2 < 0:  # the neighbour bends away: convex
            sharp[f1, k1] = sharp[f2, k2] = True
        else:
            crease[f1, k1] = crease[f2, k2] = True
    T = V[F]
    alt = np.zeros((m, 3))
    for k in range(3):
        a, b = T[:, (k + 1) % 3], T[:, (k + 2) % 3]
        base = np.linalg.norm(b - a, axis=1)
        area2 = np.linalg.norm(np.cross(b - a, T[:, k] - a), axis=1)
        alt[:, k] = area2 / np.maximum(base, 1e-12)
    return sharp, crease, alt


def _principal_axis(V: np.ndarray) -> np.ndarray:
    c = V - V.mean(0)
    w, vec = np.linalg.eigh(c.T @ c)
    ax = vec[:, np.argmax(w)]
    i = np.argmax(np.abs(ax))
    return ax if ax[i] > 0 else -ax  # deterministic sign


def _rasterize_uv(uv_px: np.ndarray, res: int):
    """(m,3,2) pixel-space triangles -> texel index, face index, barycentrics for covered texels."""
    idx, fid, bary = [], [], []
    for t in range(len(uv_px)):
        (x0, y0), (x1, y1), (x2, y2) = uv_px[t]
        area = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
        if abs(area) < 1e-12:
            continue
        minx, maxx = max(int(np.floor(min(x0, x1, x2))), 0), min(int(np.ceil(max(x0, x1, x2))), res - 1)
        miny, maxy = max(int(np.floor(min(y0, y1, y2))), 0), min(int(np.ceil(max(y0, y1, y2))), res - 1)
        if minx > maxx or miny > maxy:
            continue
        px, py = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
        b0 = ((x1 - px) * (y2 - py) - (y1 - py) * (x2 - px)) / area
        b1 = ((x2 - px) * (y0 - py) - (y2 - py) * (x0 - px)) / area
        b2 = 1 - b0 - b1
        inside = (b0 >= -1e-6) & (b1 >= -1e-6) & (b2 >= -1e-6)
        if not inside.any():
            continue
        ys, xs = np.nonzero(inside)
        idx.append((ys + miny) * res + (xs + minx))
        fid.append(np.full(len(ys), t))
        bary.append(np.stack([b0[inside], b1[inside], b2[inside]], 1))
    if not idx:
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros((0, 3))
    return np.concatenate(idx), np.concatenate(fid), np.clip(np.concatenate(bary), 0, 1)


def _dilate(img: np.ndarray, filled: np.ndarray, steps: int) -> np.ndarray:
    img, filled = img.copy(), filled.copy()
    for _ in range(steps):
        acc = np.zeros_like(img)
        cnt = np.zeros(filled.shape)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            sh_f = np.roll(filled, (dy, dx), (0, 1))
            sh_i = np.roll(img, (dy, dx), (0, 1))
            acc += sh_i * sh_f[..., None]
            cnt += sh_f
        grow = (~filled) & (cnt > 0)
        img[grow] = acc[grow] / cnt[grow][:, None]
        filled |= grow
    return img


# ------------------------------------------------------------------ images


def _load_image(asset_dir: Path, rel: str) -> np.ndarray:
    from PIL import Image

    p = Path(rel)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"image path '{rel}' must be relative and stay inside the asset directory")
    full = (asset_dir / p).resolve()
    if asset_dir.resolve() not in full.parents or full.suffix.lower() not in IMAGE_TYPES or not full.exists():
        raise ValueError(f"image '{rel}' not found or not PNG/JPEG inside the asset directory")
    if full.stat().st_size > LIMITS.max_image_bytes:
        raise ValueError(f"image '{rel}' larger than {LIMITS.max_image_bytes} bytes")
    with Image.open(full) as im:
        if max(im.size) > LIMITS.max_texture_size:
            raise ValueError(f"image '{rel}' is {im.size}, larger than {LIMITS.max_texture_size}px")
        return np.asarray(im.convert("RGB"), dtype=np.float64) / 255.0


def _sample(img: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bilinear, wrapping. u, v in texture repeats."""
    h, w = img.shape[:2]
    x, y = (u % 1.0) * w - 0.5, (1 - (v % 1.0)) * h - 0.5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    g = lambda yy, xx: img[yy % h, xx % w]  # noqa: E731
    return (g(y0, x0) * (1 - fx) * (1 - fy) + g(y0, x0 + 1) * fx * (1 - fy) + g(y0 + 1, x0) * (1 - fx) * fy + g(y0 + 1, x0 + 1) * fx * fy)


def _triplanar(img, P, N, scale):
    w = np.abs(N) ** 4
    w /= np.maximum(w.sum(1, keepdims=True), 1e-12)
    q = P / scale
    return (_sample(img, q[:, 2], q[:, 1]) * w[:, :1] + _sample(img, q[:, 0], q[:, 2]) * w[:, 1:2] + _sample(img, q[:, 0], q[:, 1]) * w[:, 2:3])


# ------------------------------------------------------------------ main


def _resolution(asset: Asset, surface: Surface, target: float) -> tuple[int, int, float]:
    area3d, uv_area = 0.0, 0.0
    seen = set()
    for p in asset.parts:
        sp = surface.parts[p.name]
        if sp.uv_owner in seen or sp.corner_uv is None:
            continue
        seen.add(sp.uv_owner)
        _, a = p.mesh.face_normals()
        uv = sp.corner_uv
        a2 = 0.5 * np.abs((uv[:, 1, 0] - uv[:, 0, 0]) * (uv[:, 2, 1] - uv[:, 0, 1]) - (uv[:, 2, 0] - uv[:, 0, 0]) * (uv[:, 1, 1] - uv[:, 0, 1]))
        area3d += a.sum()
        uv_area += a2.sum()
    need = target * np.sqrt(area3d / max(uv_area, 1e-12))
    needed = int(2 ** np.ceil(np.log2(max(need, 64))))
    cap = int(min(asset.budget.get("texture_size", 1024), LIMITS.max_texture_size))
    res = max(64, min(needed, cap))
    return res, needed, float(res * np.sqrt(uv_area / max(area3d, 1e-12)))


def bake(asset: Asset, surface: Surface) -> Textures | None:
    if not needs_textures(asset) or surface.uv_method == "none":
        return None
    target = float((asset.uv or {}).get("texel_density") or asset.budget.get("texel_density", 256))
    res, needed, achieved = _resolution(asset, surface, target)
    base = np.zeros((res * res, 3))
    orm = np.zeros((res * res, 3))
    orm[:, 0] = 1.0
    covered = np.zeros(res * res, dtype=bool)
    tex = Textures(res, None, None, None, None, target, achieved, needed)
    images: dict = {}
    stats: dict = {}
    seen_owner = set()
    ground = min(float(p.mesh.V[:, 1].min()) for p in asset.parts if len(p.mesh.V))
    for p in asset.parts:
        sp = surface.parts[p.name]
        if sp.corner_uv is None or sp.uv_owner in seen_owner:
            continue  # shared-UV instances reuse the first instance's texels
        seen_owner.add(sp.uv_owner)
        mesh = p.mesh
        texel, fid, bary = _rasterize_uv(np.stack([sp.corner_uv[..., 0] * res, (1 - sp.corner_uv[..., 1]) * res], -1), res)
        if not len(texel):
            continue
        T = mesh.V[mesh.F]
        P = np.einsum("kc,kcd->kd", bary, T[fid])
        fn, _ = mesh.face_normals()
        N = fn[fid]
        sharp, crease, alt = _sharp_edges(mesh)
        dist = np.where(sharp[fid], bary * alt[fid], np.inf).min(1)
        cdist = np.where(crease[fid], bary * alt[fid], np.inf).min(1)
        height = P[:, 1] - ground
        axis = _principal_axis(mesh.V)
        mats = np.array([m if m else p.material for m in mesh.label_values("material")], dtype=object)[fid]
        part_seed = zlib.crc32(p.base.encode()) % 997
        for mname in dict.fromkeys(mats):
            sel = mats == mname
            mat = asset.materials.get(mname or "")
            if mat is None:
                base[texel[sel]] = [0.8, 0.8, 0.8]
                orm[texel[sel], 1] = 0.8
                continue
            arch = M.ARCHETYPES[mat["archetype"]]
            from .source import parse_color_value

            a = {pp.name: (parse_color_value(pp.default) if pp.kind == "color" else pp.default) for pp in arch.params}
            a.update(mat["args"])
            a["color"] = np.asarray(mat["base_color"][:3])
            s = M.Samples(P[sel], N[sel], np.clip(1 - dist[sel] / a["edge_width"], 0, 1), axis, mesh.center(), part_seed,
                          cavity=np.clip(1 - cdist[sel] / (2 * a["edge_width"]), 0, 1), height=height[sel])
            ch = M.apply_grime(a, s, arch.fn(a, s))
            col = ch.base
            for li, lay in enumerate(mat["layers"]):
                where = f"materials.{mname}.layers[{li}]"
                if lay["vertex_color"] and "color" in mesh.vattr:
                    vc = np.einsum("kc,kcd->kd", bary[sel], mesh.vattr["color"][mesh.F][fid[sel]])[:, :3]
                    layer_col = col * vc
                elif lay["image"]:
                    try:
                        img = images.get(lay["image"])
                        if img is None:
                            img = images[lay["image"]] = _load_image(asset.dir, lay["image"])
                    except (ValueError, OSError) as e:
                        tex.issues.append(("TEX_IMAGE_INVALID", "error", str(e), where, "PNG/JPEG inside the asset directory, within size limits"))
                        continue
                    if lay["projection"] == "uv":
                        if "uv" in mesh.cattr and "uv" not in mesh.invalidated:
                            uvs = np.einsum("kc,kcd->kd", bary[sel], mesh.cattr["uv"][fid[sel]])
                            layer_col = _sample(img, uvs[:, 0], uvs[:, 1])
                            tex.lifecycle[p.name] = "VALID"
                        else:
                            tex.lifecycle[p.name] = "INVALID"
                            tex.issues.append(("TEX_UV_SOURCE_MISSING", "warning", f"'{p.name}' has no authored UVs; image projected triplanar instead",
                                               where, "use projection: triplanar, or a mesh_file part with UVs"))
                            layer_col = _triplanar(img, P[sel], N[sel], lay["scale"])
                    else:
                        layer_col = _triplanar(img, P[sel], N[sel], lay["scale"])
                    if lay["tint"] is not None:
                        layer_col = layer_col * np.asarray(lay["tint"][:3])
                else:
                    continue
                w = np.full(sel.sum(), lay["opacity"])
                edge_w = s.edge
                if lay["mask"] == "edge":
                    w = w * edge_w
                elif lay["mask"] == "inverse_edge":
                    w = w * (1 - edge_w)
                col = col + (layer_col - col) * w[:, None]
            base[texel[sel]] = np.clip(col, 0, 1)
            orm[texel[sel], 1] = np.clip(ch.roughness, 0, 1)
            orm[texel[sel], 2] = np.clip(ch.metallic, 0, 1)
            st = stats.setdefault(mname, {"texels": 0, "base_sum": np.zeros(3), "metal_mid": 0, "metal_sum": 0.0})
            st["texels"] += int(sel.sum())
            st["base_sum"] += col.sum(0)
            st["metal_sum"] += float(ch.metallic.sum())
            st["metal_mid"] += int(((ch.metallic > 0.2) & (ch.metallic < 0.8)).sum())
        covered[texel] = True
        tex.lifecycle.setdefault(p.name, "DERIVED")
    cov2 = covered.reshape(res, res)
    pad = int((asset.uv or {}).get("padding_px", (asset.profile.get("uv") or {}).get("padding_px", 4))) + 2
    tex.base = _dilate(base.reshape(res, res, 3), cov2, pad)
    tex.orm = _dilate(orm.reshape(res, res, 3), cov2, pad)
    tex.covered = cov2
    edge = np.zeros_like(cov2)
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        edge |= cov2 & ~np.roll(cov2, (dy, dx), (0, 1))
    tex.seams = edge
    for mname, st in stats.items():
        n = max(st["texels"], 1)
        tex.material_stats[mname] = {"mean_srgb": [int(round(v * 255)) for v in st["base_sum"] / n],
                                     "metallic_mean": round(st["metal_sum"] / n, 3), "metallic_mixed_fraction": round(st["metal_mid"] / n, 3),
                                     "texels": st["texels"]}
    if surface.lock == "stale":
        for k, v in tex.lifecycle.items():
            if v == "VALID":
                tex.lifecycle[k] = "RELAYOUT"
    elif surface.lock_notes:
        for k in surface.lock_notes:
            if tex.lifecycle.get(k) == "VALID":
                tex.lifecycle[k] = "REGION_KEPT"
    return tex


def textures_for(asset: Asset, surface: Surface) -> Textures | None:
    """Cached per surface object (render, validation and export share one bake)."""
    if not hasattr(surface, "_textures"):
        surface._textures = bake(asset, surface)
    return surface._textures


def to_png_bytes(arr: np.ndarray) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8)).save(buf, format="PNG", optimize=False)
    return buf.getvalue()
