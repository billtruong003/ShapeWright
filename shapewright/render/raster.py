"""Deterministic CPU triangle rasterizer (numpy).

Why not a GPU / browser renderer? For the inspection loop the requirements are
(1) runs in any headless container with no GPU or display, (2) byte-identical
output for identical input so iterations can be diffed, and (3) small assets
(hundreds to tens of thousands of triangles). A z-buffer rasterizer in numpy
meets all three with no system dependencies. Photoreal rendering is not a
goal; legibility for a vision model is.
"""

from __future__ import annotations

import numpy as np


class Buffers:
    def __init__(self, w: int, h: int, extra_dim: int = 0):
        self.w, self.h = w, h
        self.extra = np.zeros((h, w, extra_dim)) if extra_dim else None
        self.depth = np.full((h, w), -np.inf)  # larger = closer
        self.tri = np.full((h, w), -1, dtype=np.int64)
        self.normal = np.zeros((h, w, 3))
        self.front = np.zeros((h, w), dtype=bool)


def edge(ax, ay, bx, by, px, py):
    return (bx - ax) * (py - ay) - (by - ay) * (px - ax)


def rasterize(screen: np.ndarray, key: np.ndarray, normals: np.ndarray, front: np.ndarray, w: int, h: int,
              extra: np.ndarray | None = None) -> Buffers:
    """screen: (m,3,2) pixel coords; key: (m,3) closeness (interpolated linearly);
    normals: (m,3,3) per-corner normals; front: (m,) front-facing flags;
    extra: optional (m,3,k) per-corner attributes (e.g. UVs) interpolated into buf.extra."""
    buf = Buffers(w, h, 0 if extra is None else extra.shape[2])
    for t in range(len(screen)):
        (x0, y0), (x1, y1), (x2, y2) = screen[t]
        area = edge(x0, y0, x1, y1, x2, y2)
        if abs(area) < 1e-12:
            continue
        minx, maxx = max(int(np.floor(min(x0, x1, x2))), 0), min(int(np.ceil(max(x0, x1, x2))), w - 1)
        miny, maxy = max(int(np.floor(min(y0, y1, y2))), 0), min(int(np.ceil(max(y0, y1, y2))), h - 1)
        if minx > maxx or miny > maxy:
            continue
        px, py = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
        b0 = edge(x1, y1, x2, y2, px, py) / area
        b1 = edge(x2, y2, x0, y0, px, py) / area
        b2 = 1.0 - b0 - b1
        inside = (b0 >= 0) & (b1 >= 0) & (b2 >= 0)
        if not inside.any():
            continue
        k = b0 * key[t, 0] + b1 * key[t, 1] + b2 * key[t, 2]
        region = buf.depth[miny:maxy + 1, minx:maxx + 1]
        win = inside & (k > region)
        if not win.any():
            continue
        region[win] = k[win]
        buf.tri[miny:maxy + 1, minx:maxx + 1][win] = t
        n = b0[..., None] * normals[t, 0] + b1[..., None] * normals[t, 1] + b2[..., None] * normals[t, 2]
        buf.normal[miny:maxy + 1, minx:maxx + 1][win] = n[win]
        buf.front[miny:maxy + 1, minx:maxx + 1][win] = front[t]
        if extra is not None:
            e = b0[..., None] * extra[t, 0] + b1[..., None] * extra[t, 1] + b2[..., None] * extra[t, 2]
            buf.extra[miny:maxy + 1, minx:maxx + 1][win] = e[win]
    length = np.linalg.norm(buf.normal, axis=2, keepdims=True)
    buf.normal = np.where(length > 1e-12, buf.normal / np.maximum(length, 1e-12), 0)
    return buf


def coverage(tris2d: np.ndarray, w: int, h: int, owner: np.ndarray | None = None):
    """Count how many triangles cover each pixel centre (used for UV overlap).

    tris2d: (m,3,2) pixel coords. Returns (count[h,w], last_owner[h,w]).
    """
    count = np.zeros((h, w), dtype=np.int32)
    who = np.full((h, w), -1, dtype=np.int64)
    for t in range(len(tris2d)):
        (x0, y0), (x1, y1), (x2, y2) = tris2d[t]
        area = edge(x0, y0, x1, y1, x2, y2)
        if abs(area) < 1e-12:
            continue
        minx, maxx = max(int(np.floor(min(x0, x1, x2))), 0), min(int(np.ceil(max(x0, x1, x2))), w - 1)
        miny, maxy = max(int(np.floor(min(y0, y1, y2))), 0), min(int(np.ceil(max(y0, y1, y2))), h - 1)
        if minx > maxx or miny > maxy:
            continue
        px, py = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
        b0 = edge(x1, y1, x2, y2, px, py) / area
        b1 = edge(x2, y2, x0, y0, px, py) / area
        b2 = 1.0 - b0 - b1
        eps = 1e-7
        inside = (b0 > eps) & (b1 > eps) & (b2 > eps)
        count[miny:maxy + 1, minx:maxx + 1] += inside
        who[miny:maxy + 1, minx:maxx + 1][inside] = t if owner is None else owner[t]
    return count, who


def draw_lines(img: np.ndarray, segs: np.ndarray, color, depth: np.ndarray | None = None, seg_key: np.ndarray | None = None,
               tol: float = 0.0, alpha: float = 1.0):
    """Draw 2D segments (n,2,2) into img (h,w,3); optional depth test against a closeness buffer."""
    h, w = img.shape[:2]
    color = np.asarray(color, dtype=np.float64)
    for i, ((x0, y0), (x1, y1)) in enumerate(segs):
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 2
        t = np.linspace(0, 1, n)
        xs = np.round(x0 + (x1 - x0) * t - 0.5).astype(int)
        ys = np.round(y0 + (y1 - y0) * t - 0.5).astype(int)
        ok = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
        if depth is not None and seg_key is not None:
            k = seg_key[i, 0] + (seg_key[i, 1] - seg_key[i, 0]) * t
            ok &= np.where(ok, k >= depth[np.clip(ys, 0, h - 1), np.clip(xs, 0, w - 1)] - tol, False)
        img[ys[ok], xs[ok]] = img[ys[ok], xs[ok]] * (1 - alpha) + color * alpha
