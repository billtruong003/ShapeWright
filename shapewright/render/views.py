"""Deterministic inspection renders: cameras, modes, overlays, contact sheets.

Every view is fully determined by (asset geometry, view name, mode, size,
frame bounds). The same asset renders to the same pixels on every run, and two
iterations framed with the same bounds are directly comparable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..assemble import Asset
from ..surface import Surface
from .raster import coverage, draw_lines, rasterize

BG = np.array([0.925, 0.918, 0.902])
CLAY = np.array([0.80, 0.78, 0.74])
GHOST = np.array([0.86, 0.86, 0.86])
FOCUS = np.array([0.95, 0.55, 0.15])
BACKFACE = np.array([1.0, 0.0, 1.0])
PALETTE = [
    (0.90, 0.36, 0.30), (0.25, 0.55, 0.85), (0.35, 0.72, 0.38), (0.95, 0.70, 0.20), (0.62, 0.42, 0.80),
    (0.20, 0.75, 0.75), (0.90, 0.50, 0.70), (0.55, 0.55, 0.25), (0.40, 0.40, 0.75), (0.85, 0.60, 0.45),
    (0.30, 0.45, 0.35), (0.70, 0.25, 0.45),
]


@dataclass(frozen=True)
class View:
    name: str
    direction: tuple  # from target toward the eye
    up: tuple
    ortho: bool
    doc: str


def _dir(az, el):
    a, e = math.radians(az), math.radians(el)
    return (math.sin(a) * math.cos(e), math.sin(e), math.cos(a) * math.cos(e))


VIEWS = {
    "front": View("front", (0, 0, 1), (0, 1, 0), True, "orthographic, looking at the +Z face"),
    "back": View("back", (0, 0, -1), (0, 1, 0), True, "orthographic, looking at the -Z face"),
    "left": View("left", (-1, 0, 0), (0, 1, 0), True, "orthographic, looking at the -X side"),
    "right": View("right", (1, 0, 0), (0, 1, 0), True, "orthographic, looking at the +X side"),
    "top": View("top", (0, 1, 0), (0, 0, -1), True, "orthographic plan view, front at the bottom"),
    "bottom": View("bottom", (0, -1, 0), (0, 0, 1), True, "orthographic, from below"),
    "front_right": View("front_right", _dir(35, 22), (0, 1, 0), False, "perspective 3/4 from front-right"),
    "front_left": View("front_left", _dir(-35, 22), (0, 1, 0), False, "perspective 3/4 from front-left"),
    "back_right": View("back_right", _dir(145, 22), (0, 1, 0), False, "perspective 3/4 from back-right"),
    "back_left": View("back_left", _dir(-145, 22), (0, 1, 0), False, "perspective 3/4 from back-left"),
    "low_front": View("low_front", _dir(20, -8), (0, 1, 0), False, "perspective, near ground level (player eye on props)"),
}

MODES = {
    "clay": "neutral shaded form with outlines; best for proportions and silhouette",
    "parts": "each semantic part in its own colour with a legend",
    "material": "material base colours, shaded",
    "wire": "clay plus triangle edges (topology density)",
    "normals": "world-space normals as RGB; magenta never appears for correct winding",
    "silhouette": "black shape on white; readability at a distance",
    "provenance": "faces coloured by the geometry expression that created them (e.g. boolean cut faces), with legend",
    "regions": "faces coloured by surface region (top/bottom/side/bevel/cut...), with legend",
}
FOV = 30.0


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


class Camera:
    def __init__(self, view: View, bounds: np.ndarray, w: int, h: int, margin: float = 0.12):
        self.view, self.w, self.h = view, w, h
        d = np.asarray(view.direction, dtype=np.float64)
        d /= np.linalg.norm(d)
        target = (bounds[0] + bounds[1]) / 2
        radius = max(np.linalg.norm(bounds[1] - bounds[0]) / 2, 1e-3)
        fwd = -d
        right = np.cross(fwd, np.asarray(view.up, dtype=np.float64))
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        self.right, self.up, self.fwd, self.target = right, up, fwd, target
        corners = np.array([[bounds[i][0], bounds[j][1], bounds[k][2]] for i in (0, 1) for j in (0, 1) for k in (0, 1)])
        if view.ortho:
            rel = corners - target
            half_w = np.abs(rel @ right).max()
            half_h = np.abs(rel @ up).max()
            self.scale = min(w / (2 * half_w), h / (2 * half_h)) / (1 + 2 * margin) if half_w > 0 and half_h > 0 else 1.0
            self.eye = target + d * radius * 4
        else:
            f = (h / 2) / math.tan(math.radians(FOV) / 2)
            self.focal = f
            dist = radius / math.sin(math.radians(FOV) / 2) * (1 + margin)
            self.eye = target + d * dist

    def project(self, P: np.ndarray):
        """World points (...,3) -> (screen xy (...,2), closeness key (...,))."""
        rel = P - self.eye
        x, y, z = rel @ self.right, rel @ self.up, rel @ self.fwd
        if self.view.ortho:
            tx = (P - self.target) @ self.right
            ty = (P - self.target) @ self.up
            sx = self.w / 2 + tx * self.scale
            sy = self.h / 2 - ty * self.scale
            return np.stack([sx, sy], -1), -z
        z = np.maximum(z, 1e-6)
        sx = self.w / 2 + self.focal * x / z
        sy = self.h / 2 - self.focal * y / z
        return np.stack([sx, sy], -1), 1.0 / z

    def facing(self, centers: np.ndarray, normals: np.ndarray) -> np.ndarray:
        to_eye = -self.fwd[None, :] if self.view.ortho else self.eye[None, :] - centers
        return np.einsum("ij,ij->i", normals, to_eye) > 0


def part_colors(asset: Asset) -> dict[str, np.ndarray]:
    bases = list(dict.fromkeys(p.base for p in asset.parts))
    return {b: np.array(PALETTE[i % len(PALETTE)]) for i, b in enumerate(bases)}


def _srgb(c):
    return np.asarray(c[:3], dtype=np.float64)


def render(asset: Asset, surface: Surface, view_name: str = "front_right", mode: str = "clay", size: int = 512,
           focus: list[str] | None = None, isolate: bool = False, frame: np.ndarray | None = None,
           supersample: int = 2, annotate: bool = True, label: str = "") -> Image.Image:
    view = VIEWS[view_name]
    W = H = size * supersample
    parts = asset.parts
    focus_set = set()
    for f in focus or []:
        focus_set |= {p.name for p in asset.parts_named(f)}
    if isolate and focus_set:
        parts = [p for p in parts if p.name in focus_set]
    bounds = frame if frame is not None else (np.stack([np.min([p.bounds[0] for p in parts], 0), np.max([p.bounds[1] for p in parts], 0)]))
    cam = Camera(view, bounds, W, H)

    tris, nrms, fnorm, owner, labels = [], [], [], [], []
    for pi, p in enumerate(parts):
        if mode in ("provenance", "regions"):
            labels.append(p.mesh.label_values("origin" if mode == "provenance" else "region"))
        elif mode == "material":
            fm = surface.parts[p.name].face_material
            labels.append(np.array([m if m else p.material for m in fm], dtype=object))
        sp = surface.parts[p.name]
        tris.append(sp.positions[sp.indices].astype(np.float64))
        nrms.append(sp.normals[sp.indices].astype(np.float64))
        fn, _ = p.mesh.face_normals()
        fnorm.append(fn)
        owner.append(np.full(len(sp.indices), pi))
    T = np.concatenate(tris)
    N = np.concatenate(nrms)
    FN = np.concatenate(fnorm)
    OWN = np.concatenate(owner)
    scr, key = cam.project(T)
    front = cam.facing(T.mean(1), FN)
    buf = rasterize(scr, key, N, front, W, H)

    hit = buf.tri >= 0
    img = np.tile(BG if mode != "silhouette" else np.ones(3), (H, W, 1)).astype(np.float64)
    pid = np.where(hit, OWN[np.clip(buf.tri, 0, None)], -1)

    if mode == "silhouette":
        img[hit] = 0.0
    elif mode == "normals":
        img[hit] = buf.normal[hit] * 0.5 + 0.5
        img[hit & ~buf.front] = BACKFACE
    else:
        cmap = part_colors(asset)
        base = np.zeros((len(parts), 3))
        for i, p in enumerate(parts):
            base[i] = cmap[p.base] if mode == "parts" else CLAY
        tri_base = base[OWN]
        legend = {}
        if labels:
            lab = np.concatenate(labels)
            if mode == "material":
                for m in dict.fromkeys(lab):
                    mat = asset.materials.get(m or "", None)
                    tri_base[lab == m] = _srgb(mat["base_color"]) if mat else CLAY
            else:
                for k, v in enumerate(dict.fromkeys(lab)):
                    legend[str(v)] = np.array(PALETTE[k % len(PALETTE)])
                    tri_base[lab == v] = legend[str(v)]
        if focus_set and not isolate:
            tri_base = np.where(np.isin(OWN, [i for i, p in enumerate(parts) if p.name in focus_set])[:, None], FOCUS, GHOST)
        n = buf.normal
        key_l = -cam.fwd * 0.55 + cam.up * 0.55 - cam.right * 0.45
        key_l /= np.linalg.norm(key_l)
        fill_l = -cam.fwd * 0.6 + cam.right * 0.6
        fill_l /= np.linalg.norm(fill_l)
        lam = 0.42 + 0.55 * np.clip(n @ key_l, 0, 1) + 0.18 * np.clip(n @ fill_l, 0, 1) + 0.06 * n[..., 1]
        col = tri_base[np.clip(buf.tri, 0, None)] * np.clip(lam, 0, 1.25)[..., None]
        img[hit] = np.clip(col[hit], 0, 1)
        img[hit & ~buf.front] = BACKFACE

        # outlines: silhouette, part boundaries and creases make forms legible to vision models
        if mode in ("clay", "parts", "material", "wire", "provenance", "regions"):
            edge_mask = np.zeros((H, W), dtype=bool)
            for dy, dx in ((0, 1), (1, 0)):
                a = pid[: H - dy, : W - dx]
                b = pid[dy:, dx:]
                na = n[: H - dy, : W - dx]
                nb = n[dy:, dx:]
                crease = (a == b) & (a >= 0) & (np.einsum("ijk,ijk->ij", na, nb) < 0.82)
                boundary = a != b
                m = boundary | crease
                edge_mask[: H - dy, : W - dx] |= m
            thickness = max(1, supersample)
            if thickness > 1:
                em = edge_mask.copy()
                for s in range(1, thickness):
                    em[s:] |= edge_mask[:-s]
                    em[:, s:] |= edge_mask[:, :-s]
                edge_mask = em
            img[edge_mask] = img[edge_mask] * 0.25 + 0.05

    if mode == "wire":
        segs, keys = [], []
        for pi, p in enumerate(parts):
            sp = surface.parts[p.name]
            e = np.sort(np.concatenate([sp.indices[:, [0, 1]], sp.indices[:, [1, 2]], sp.indices[:, [2, 0]]]), axis=1)
            # dedupe by position so flat-shaded splits do not double edges
            pts = sp.positions.astype(np.float64)
            pk = np.round(pts[e].reshape(-1, 6), 6)
            pk = np.where((pk[:, :3] > pk[:, 3:]).any(1)[:, None], np.concatenate([pk[:, 3:], pk[:, :3]], 1), pk)
            _, first = np.unique(pk, axis=0, return_index=True)
            e = e[np.sort(first)]
            s, k = cam.project(pts[e])
            segs.append(s)
            keys.append(k)
        S = np.concatenate(segs)
        K = np.concatenate(keys)
        span = np.abs(buf.depth[hit]).max() if hit.any() else 1.0
        draw_lines(img, S, (0.1, 0.15, 0.35), buf.depth, K, tol=span * 0.004, alpha=0.85)

    out = Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)).resize((size, size), Image.LANCZOS)
    if annotate:
        _annotate(out, asset, cam, parts, view, mode, focus_set, supersample, label)
        if mode in ("provenance", "regions") and legend:
            d = ImageDraw.Draw(out)
            y = 36 if focus_set else 22
            for name, c in list(legend.items())[:14]:
                d.rectangle([6, y + 2, 16, y + 12], fill=tuple(int(v * 255) for v in c))
                d.text((20, y), name[-48:], fill=(30, 30, 30), font=_font(max(10, size // 42)))
                y += max(13, size // 34)
    return out


def _annotate(img: Image.Image, asset: Asset, cam: Camera, parts, view: View, mode: str, focus_set, ss: int, label: str):
    d = ImageDraw.Draw(img)
    size = img.size[0]
    font = _font(max(11, size // 36))
    title = label or f"{asset.name} | {view.name} | {mode}"
    d.text((6, 4), title, fill=(40, 40, 40), font=font)
    if view.ortho:
        axes = {"front": ("x", "y"), "back": ("x", "y"), "left": ("z", "y"), "right": ("z", "y"), "top": ("x", "z"), "bottom": ("x", "z")}[view.name]
        b = np.stack([np.min([p.bounds[0] for p in parts], 0), np.max([p.bounds[1] for p in parts], 0)])
        sz = b[1] - b[0]
        ai = {"x": 0, "y": 1, "z": 2}
        d.text((6, size - 18), f"{axes[0]} {sz[ai[axes[0]]]:.3f} m  x  {axes[1]} {sz[ai[axes[1]]]:.3f} m", fill=(40, 40, 40), font=font)
        # scale bar: the largest of 5 cm / 10 cm / 25 cm / 50 cm / 1 m / 2 m / 5 m that fits in a quarter of the image
        bar_m = max((v for v in (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0) if v * cam.scale / ss <= size / 4), default=0.05)
        px = bar_m * cam.scale / ss
        x1 = size - 8
        d.line([(x1 - px, size - 10), (x1, size - 10)], fill=(40, 40, 40), width=2)
        text = f"{bar_m * 100:.0f} cm" if bar_m < 1 else f"{bar_m:.0f} m"
        d.text((x1 - d.textlength(text, font=font), size - 26), text, fill=(40, 40, 40), font=font)
        if view.name in ("front", "back", "left", "right"):  # ground line
            gy = (cam.h / 2 - (0 - cam.target[1]) * cam.scale) / ss
            if 0 <= gy < size:
                d.line([(0, gy), (size, gy)], fill=(150, 150, 150), width=1)
    if mode == "parts" and not focus_set:
        cmap = part_colors(asset)
        y = 22
        shown = list(dict.fromkeys(p.base for p in parts))
        for base in shown[:14]:
            c = tuple(int(v * 255) for v in cmap[base])
            d.rectangle([6, y + 2, 16, y + 12], fill=c)
            d.text((20, y), base, fill=(30, 30, 30), font=_font(max(10, size // 42)))
            y += max(13, size // 34)
        if len(shown) > 14:
            d.text((6, y), f"+{len(shown) - 14} more", fill=(30, 30, 30), font=font)
    if focus_set:
        d.text((6, 20), "focus: " + ", ".join(sorted(focus_set))[:60], fill=(160, 70, 10), font=font)


def render_uv(asset: Asset, surface: Surface, size: int = 512, focus: list[str] | None = None) -> Image.Image:
    img = np.ones((size, size, 3)) * 0.97
    cmap = part_colors(asset)
    focus_set = set()
    for f in focus or []:
        focus_set |= {p.name for p in asset.parts_named(f)}
    tris, owner, segs = [], [], []
    for i, p in enumerate(asset.parts):
        sp = surface.parts[p.name]
        if sp.corner_uv is None:
            continue
        uv = sp.corner_uv.copy()
        px = np.stack([uv[..., 0] * size, (1 - uv[..., 1]) * size], -1)
        tris.append(px)
        owner.append(np.full(len(px), i))
        segs.append(np.concatenate([px[:, [0, 1]], px[:, [1, 2]], px[:, [2, 0]]]))
    d_img = Image.new("RGB", (size, size))
    if tris:
        T = np.concatenate(tris)
        count, who = coverage(T, size, size, np.concatenate(owner))
        base = np.array([cmap[p.base] if (not focus_set or p.name in focus_set) else GHOST for p in asset.parts])
        m = who >= 0
        img[m] = base[who[m]] * 0.75 + 0.25
        img[count > 1] = (1.0, 0.0, 0.0)
        draw_lines(img, np.concatenate(segs), (0.25, 0.25, 0.25), alpha=0.5)
    d_img = Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8))
    d = ImageDraw.Draw(d_img)
    d.rectangle([0, 0, size - 1, size - 1], outline=(0, 0, 0))
    d.text((6, 4), f"{asset.name} | UV0 ({surface.uv_resolution}px, red = overlap)", fill=(40, 40, 40), font=_font(max(11, size // 36)))
    return d_img


SHEET_TILES = [
    ("front", "clay"), ("right", "clay"), ("top", "clay"), ("front_right", "clay"),
    ("front_right", "parts"), ("back_left", "clay"), ("front_right", "wire"), ("uv", "uv"),
]


def contact_sheet(asset: Asset, surface: Surface, tile: int = 384, tiles=None, focus=None, frame=None) -> Image.Image:
    tiles = tiles or SHEET_TILES
    cols = 4
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * tile, rows * tile), (255, 255, 255))
    for i, (v, m) in enumerate(tiles):
        if m == "uv":
            im = render_uv(asset, surface, tile, focus=focus)
        else:
            im = render(asset, surface, v, m, tile, focus=focus, frame=frame)
        sheet.paste(im, ((i % cols) * tile, (i // cols) * tile))
    d = ImageDraw.Draw(sheet)
    for c in range(1, cols):
        d.line([(c * tile, 0), (c * tile, rows * tile)], fill=(255, 255, 255), width=2)
    for r in range(1, rows):
        d.line([(0, r * tile), (cols * tile, r * tile)], fill=(255, 255, 255), width=2)
    return sheet
