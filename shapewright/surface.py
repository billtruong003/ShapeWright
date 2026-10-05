"""Surface stage: per-corner normals and UVs, then export-ready vertex buffers.

UV architecture (docs/UV.md):

* **Part-owned regions.** Each UV *owner* (a part instance, or a group of
  instances sharing UVs) is charted on its own and packed into its own
  rectangle of the atlas. Chart generation for an owner depends only on that
  owner's geometry, so editing one part never moves another part's charts.
* **Deterministic layout.** Region sizes follow 3D surface area (uniform texel
  density) and are packed by a deterministic shelf packer.
* **Lock file.** `sw uv lock` writes `uv.lock.yaml` (committed, like a package
  lock): the region rectangle and geometry hash per owner. While the set of
  owners is unchanged, regions stay fixed even if areas change; only the edited
  part's charts are regenerated inside its own region.
* **Shared UVs.** `uv: {share_instances: true}` on a part makes all its
  instances (array/mirror) reuse one set of charts (intentional overlap).
* **Seams.** `uv: {seams: regions}` cuts charts along face-region boundaries
  (top/side/cap...), a data-driven substitute for hand-marked seams.
* **Authored UVs** (from `mesh_file`) are kept as charts and fitted into the
  owner's region instead of being re-unwrapped.

Legacy `uv.method: atlas` (v0.1: one global unwrap) remains available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from . import backend
from .assemble import Asset, Part
from .mesh import Mesh, geometry_hash

LOCK_NAME = "uv.lock.yaml"


@dataclass
class SurfacePart:
    name: str
    positions: np.ndarray  # (k, 3) float32
    normals: np.ndarray  # (k, 3) float32
    uvs: np.ndarray | None  # (k, 2) float32, or None
    indices: np.ndarray  # (m, 3) uint32
    corner_uv: np.ndarray | None  # (m, 3, 2) for validation
    face_material: np.ndarray  # (m,) object: material name per face (None = part material)
    colors: np.ndarray | None = None  # (k, 4) float32 linear RGBA
    uv_owner: str = ""
    authored: bool = False  # UVs are the part's own (authored material), not an atlas region
    uvs1: np.ndarray | None = None  # (k, 2) lightmap UVs (TEXCOORD_1), unique and non-overlapping across the asset
    corner_uv1: np.ndarray | None = None  # (m, 3, 2)


@dataclass
class Surface:
    parts: dict[str, SurfacePart]
    uv_method: str
    uv_resolution: int
    uv_padding: int
    uv_error: str = ""
    regions: dict = field(default_factory=dict)  # owner -> [u0, v0, u1, v1]
    owners: dict = field(default_factory=dict)  # part name -> owner
    lock: str = "none"  # none | used | stale
    lock_notes: list = field(default_factory=list)


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


# ------------------------------------------------------------------ UV owners and charts


def is_authored(asset: Asset, part) -> bool:
    """The part's material brings its own textures and UVs (docs/IMPORT.md)."""
    return bool((asset.materials.get(part.material or "") or {}).get("authored"))


def atlas_view(asset: Asset) -> Asset:
    """The asset as the atlas sees it: parts with authored materials take no atlas space."""
    import dataclasses

    keep = [p for p in asset.parts if not is_authored(asset, p)]
    return asset if len(keep) == len(asset.parts) else dataclasses.replace(asset, parts=keep)


def uv_owners(asset: Asset) -> dict[str, str]:
    """part instance name -> UV owner name."""
    out = {}
    for p in asset.parts:
        share = bool(p.uv.get("share_instances")) and (p.instance or p.name != p.base)
        out[p.name] = f"{p.base}*" if share else p.name
    return out


def _seam_split(mesh: Mesh) -> Mesh:
    """Unweld vertices across face-region boundaries so charts cannot span regions."""
    reg = mesh.fattr.get("region")
    if reg is None:
        return mesh
    key = np.stack([mesh.F.reshape(-1), np.repeat(reg, 3)], 1)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    return Mesh(mesh.V[uniq[:, 0]], inv.reshape(-1, 3))


def _charts(part: Part, resolution: int, padding: int) -> np.ndarray:
    m = part.mesh
    if "uv" in m.cattr and "uv" not in m.invalidated:
        return m.cattr["uv"].astype(np.float64)  # authored / imported UVs are kept as charts
    src = _seam_split(m) if part.uv.get("seams") == "regions" else m
    return backend.unwrap_charts(src, resolution, padding)


def _shelf_pack(items: list[tuple[str, float, float]], gutter: float) -> tuple[dict, float]:
    """items: (name, w, h) at scale 1. Returns rects at the largest scale that fits the unit square."""
    order = sorted(items, key=lambda t: (-t[2], -t[1], t[0]))

    def place(k):
        rects, x, y, row_h = {}, 0.0, 0.0, 0.0
        for name, w, h in order:
            w, h = w * k, h * k
            if x + w > 1.0 + 1e-12 and x > 0:
                x, y, row_h = 0.0, y + row_h + gutter, 0.0
            if x + w > 1.0 + 1e-12 or y + h > 1.0 + 1e-12:
                return None
            rects[name] = [x, y, x + w, y + h]
            x += w + gutter
            row_h = max(row_h, h)
        return rects

    lo, hi = 0.0, 64.0
    best = place(lo) or {}
    for _ in range(40):
        mid = (lo + hi) / 2
        r = place(mid)
        if r is None:
            hi = mid
        else:
            lo, best = mid, r
    return best, lo


def _fit(uv: np.ndarray, rect) -> np.ndarray:
    lo, hi = uv.reshape(-1, 2).min(0), uv.reshape(-1, 2).max(0)
    size = np.maximum(hi - lo, 1e-12)
    rw, rh = rect[2] - rect[0], rect[3] - rect[1]
    s = min(rw / size[0], rh / size[1])
    return (uv - lo) * s + np.array([rect[0], rect[1]])


def read_lock(asset_dir: Path) -> dict | None:
    p = asset_dir / LOCK_NAME
    return yaml.safe_load(p.read_text()) if p.exists() else None


def _part_resolution(resolution: int, area: float, total: float) -> int:
    """Resolution to chart one part at: about the pixel size of the atlas region it will get, as a power of two
    (64..resolution). Charting every part at the full atlas resolution cost 0.11 s per part at 2048 px and made a
    571-part house take 95 s to lay out, although each part lands in a region a few dozen pixels wide
    (MODULAR_HOUSE_PACK_01). Regions are still sized by area afterwards; only the charting grid changes."""
    est = resolution * np.sqrt(area / max(total, 1e-12)) * 2.0
    return int(min(resolution, max(64, 2 ** int(np.ceil(np.log2(max(est, 1.0)))))))


def compute_layout(asset: Asset, resolution: int, padding: int, unique: bool = False):
    """unique: every part instance gets its own charts (lightmaps: no two surfaces may share texels)."""
    if not unique:
        asset = atlas_view(asset)
    owners = {p.name: p.name for p in asset.parts} if unique else uv_owners(asset)
    first = {}
    for p in asset.parts:
        first.setdefault(owners[p.name], p)
    charts, areas = {}, {}
    for o, p in first.items():
        areas[o] = max(p.mesh.area(), 1e-12)
    total = sum(areas.values())
    for o, p in first.items():
        charts[o] = _charts(p, _part_resolution(resolution, areas[o], total), padding)
    gutter = padding / resolution
    items = []
    for o, c in charts.items():
        lo, hi = c.reshape(-1, 2).min(0), c.reshape(-1, 2).max(0)
        w, h = max(hi[0] - lo[0], 1e-9), max(hi[1] - lo[1], 1e-9)
        aspect = w / h
        # charts rarely fill their bounding box (rings and tubes pack loosely): give the region
        # the room its charts need so every part gets the same texel density (FRESH_AGENT_05)
        e1, e2 = c[:, 1] - c[:, 0], c[:, 2] - c[:, 0]
        used = 0.5 * np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]).sum()
        fill = float(np.clip(used / (w * h), 0.05, 1.0))
        need = areas[o] / fill
        items.append((o, np.sqrt(need * aspect), np.sqrt(need / aspect)))
    rects, _ = _shelf_pack(items, gutter)
    return owners, first, charts, rects


def write_lock(asset: Asset) -> Path:
    uv_cfg = asset.uv or {}
    resolution = int(uv_cfg.get("resolution", asset.budget.get("texture_size", 1024)))
    padding = int(uv_cfg.get("padding_px", (asset.profile.get("uv") or {}).get("padding_px", 4)))
    owners, first, charts, rects = compute_layout(asset, resolution, padding)
    data = {
        "version": 1, "resolution": resolution, "padding_px": padding,
        "owners": {o: {"rect": [round(float(v), 6) for v in rects[o]], "geometry": geometry_hash(first[o].mesh)} for o in sorted(rects)},
    }
    p = asset.dir / LOCK_NAME
    p.write_text("# Generated by `sw uv lock`. Commit it: keeps each part's UV region fixed across edits.\n"
                 "# Re-run after adding/removing parts. See docs/UV.md.\n" + yaml.safe_dump(data, sort_keys=False))
    return p


def _unwrap_regions(asset: Asset, resolution: int, padding: int, surface: Surface) -> dict[str, np.ndarray]:
    asset = atlas_view(asset)
    owners, first, charts, rects = compute_layout(asset, resolution, padding)
    lock = read_lock(asset.dir)
    if lock:
        locked = lock.get("owners") or {}
        if set(locked) == set(charts):
            rects = {o: locked[o]["rect"] for o in charts}
            surface.lock = "used"
            for o in sorted(charts):
                if locked[o].get("geometry") != geometry_hash(first[o].mesh):
                    surface.lock_notes.append(o)
        else:
            surface.lock = "stale"
            surface.lock_notes = sorted(set(charts) ^ set(locked))
    surface.regions = rects
    surface.owners = owners
    fitted = {o: _fit(c, rects[o]) for o, c in charts.items()}
    out = {}
    for p in asset.parts:
        o = owners[p.name]
        uv = fitted[o]
        base = first[o]
        if base.name != p.name:
            if len(uv) != p.mesh.n_tris:
                uv = _fit(_charts(p, resolution, padding), rects[o])  # topology differs: own charts, same region
            elif p.instance.get("reflected", 0) != base.instance.get("reflected", 0):
                uv = uv[:, ::-1]  # mirror twins have reversed winding
        out[p.name] = uv
    return out


def _unwrap_atlas(asset: Asset, resolution: int, padding: int) -> dict[str, np.ndarray]:
    """v0.1 behaviour: one global unwrap (unstable across edits)."""
    asset = atlas_view(asset)
    from .mesh import concat

    whole = concat([p.mesh for p in asset.parts])
    corner = backend.unwrap_charts(whole, resolution, padding)
    out, start = {}, 0
    for p in asset.parts:
        out[p.name] = corner[start:start + p.mesh.n_tris]
        start += p.mesh.n_tris
    return out


def _vertex_material_colors(asset: Asset, part, pos: np.ndarray) -> np.ndarray | None:
    """(m,3,4) linear RGBA per corner for faces whose material is `archetype: vertex` (white elsewhere), or None.
    Colour x a shade toward the part's bottom x a seeded per-part variation. When the asset also bakes an atlas,
    the colour itself comes from the atlas and only the shade goes to the vertices."""
    import zlib

    from .bake import needs_textures
    from .export.gltf import srgb_to_linear

    mats = [m if m else part.material for m in part.mesh.label_values("material")]
    vert = {m for m in set(mats) if (asset.materials.get(m or "") or {}).get("archetype") == "vertex"}
    if not vert:
        return None
    out = np.ones((len(mats), 3, 4))
    y = pos[..., 1]
    lo, hi = float(y.min()), float(y.max())
    t = (y - lo) / max(hi - lo, 1e-6)  # 0 at the bottom of the part, 1 at the top
    textured = needs_textures(asset)
    for m in vert:
        mat = asset.materials[m]
        a = mat["args"]
        sel = np.array([x == m for x in mats])
        rnd = zlib.crc32(part.base.encode()) / 2**32 - 0.5
        k = (1.0 - float(a.get("bottom_shade", 0.25)) * (1 - t[sel])) * (1.0 + float(a.get("variation", 0.0)) * rnd)
        base = np.ones(3) if textured else np.asarray(srgb_to_linear(mat["base_color"][:3]))
        out[sel, :, :3] = np.clip(k[..., None] * base, 0, 1)
    return out


def lightmap_uvs(asset: Asset, resolution: int, padding: int) -> dict[str, np.ndarray]:
    """Phase 21: a second UV set for baked lighting (Unity/Unreal static lightmaps): every part, authored ones
    included, charted on its own and packed without overlap, regions sized by area (uniform lightmap density)."""
    _, first, charts, rects = compute_layout(asset, resolution, padding, unique=True)
    return {o: _fit(c, rects[o]) for o, c in charts.items()}


def lightmap_enabled(asset: Asset) -> bool:
    uv_cfg = asset.uv or {}
    return bool(uv_cfg.get("lightmap", (asset.profile.get("uv") or {}).get("lightmap", False)))


# ------------------------------------------------------------------ build


def build_surface(asset: Asset, corner_uvs_given: dict | None = None) -> Surface:
    """corner_uvs_given: part name -> (m,3,2) UVs to use instead of unwrapping (LODs keep LOD0's atlas)."""
    uv_cfg = asset.uv or {}
    method = uv_cfg.get("method", "regions")
    if method == "auto":
        method = "regions"
    resolution = int(uv_cfg.get("resolution", asset.budget.get("texture_size", 1024)))
    padding = int(uv_cfg.get("padding_px", (asset.profile.get("uv") or {}).get("padding_px", 4)))
    from . import trim

    trim_cfg = trim.config(asset)
    if trim_cfg and corner_uvs_given is None:
        method, resolution = "trim", trim_cfg["size"]
    surface = Surface({}, method, resolution, padding)
    corner_uvs: dict = dict(corner_uvs_given or {})
    if corner_uvs_given is not None:
        pass
    elif method == "trim":  # Phase 21: the pack's shared trim sheet
        surface.trim = trim_cfg
        surface.trim_density = {}
        for p in atlas_view(asset).parts:
            corner_uvs[p.name], surface.trim_density[p.name] = trim.corner_uvs(p, trim_cfg)
    elif method in ("regions", "atlas"):
        try:
            corner_uvs = (_unwrap_regions(asset, resolution, padding, surface) if method == "regions"
                          else _unwrap_atlas(asset, resolution, padding))
        except Exception as e:  # missing binary wheel or atlas failure
            surface.uv_error = str(e)
            surface.uv_method = "none"
            corner_uvs = {}
    uv1 = {}
    if lightmap_enabled(asset) and corner_uvs_given is None:
        lm_res = int((asset.uv or {}).get("lightmap_resolution", 1024))
        uv1 = lightmap_uvs(asset, lm_res, max(4, padding))
        surface.lightmap_resolution = lm_res
    for p in asset.parts:
        auth = is_authored(asset, p)
        if auth:  # authored textures map through the part's own UVs, unchanged
            cuv = p.mesh.cattr["uv"].astype(np.float64) if "uv" in p.mesh.cattr and "uv" not in p.mesh.invalidated else None
        else:
            cuv = corner_uvs.get(p.name)
        pos = p.mesh.V[p.mesh.F]  # (m,3,3)
        nrm = corner_normals(p.mesh, p.shading, p.smooth_angle)
        cols = [pos.reshape(-1, 3), nrm.reshape(-1, 3)]
        if cuv is not None:
            cols.append(cuv.reshape(-1, 2))
        c1 = uv1.get(p.name)
        if c1 is not None:
            cols.append(c1.reshape(-1, 2))
        col = p.mesh.vattr.get("color")
        vcol = _vertex_material_colors(asset, p, pos)
        if vcol is not None:  # Phase 21: `archetype: vertex` materials bake into COLOR_0
            corner = col[p.mesh.F] if col is not None else np.ones((len(p.mesh.F), 3, 4))
            cols.append((corner * vcol).reshape(-1, 4))
            col = np.ones((len(p.mesh.V), 4))  # marks "has colours" below; the per-corner values are in cols
        elif col is not None:
            cols.append(col[p.mesh.F].reshape(-1, 4))
        key = np.round(np.concatenate(cols, axis=1), 6)
        _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
        rank = np.empty(len(first), dtype=np.int64)
        rank[np.argsort(first, kind="stable")] = np.arange(len(first))
        sel = np.sort(first)
        mats = p.mesh.label_values("material")
        surface.parts[p.name] = SurfacePart(
            p.name,
            cols[0][sel].astype(np.float32),
            cols[1][sel].astype(np.float32),
            cols[2][sel].astype(np.float32) if cuv is not None else None,
            rank[inverse.reshape(-1)].reshape(-1, 3).astype(np.uint32),
            cuv,
            mats,
            cols[-1][sel].astype(np.float32) if col is not None else None,
            surface.owners.get(p.name, p.name),
            auth,
            cols[3 if cuv is not None else 2][sel].astype(np.float32) if c1 is not None else None,
            c1,
        )
    return surface
