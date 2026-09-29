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


_CLASSES = (2, 4, 8, 16, 32)  # larger triangles use their exact box, one at a time
_BATCH = 4_000_000  # candidate pixels evaluated per numpy batch


def fragments(screen: np.ndarray, w: int, h: int, test: str = "closed", order: str = "any"):
    """Pixel centres covered by each triangle, vectorized (Phase 10: replaces per-triangle Python loops).

    screen: (m,3,2) pixel coordinates. test: "closed" (b >= 0, the renderer's rule), "open" (b > 1e-7,
    UV coverage), "bake" (the texture baker's formula, b >= -1e-6). Returns (t, px, py, b0, b1, b2) with the same floating-point arithmetic as the
    former per-triangle loop, so results are bit-identical. order="triangle" sorts by (t, py, px),
    the loop's order, for callers whose later writes win.
    """
    x0, y0 = screen[:, 0, 0], screen[:, 0, 1]
    x1, y1 = screen[:, 1, 0], screen[:, 1, 1]
    x2, y2 = screen[:, 2, 0], screen[:, 2, 1]
    area = edge(x0, y0, x1, y1, x2, y2)
    minx = np.maximum(np.floor(np.minimum(np.minimum(x0, x1), x2)), 0).astype(np.int64)
    maxx = np.minimum(np.ceil(np.maximum(np.maximum(x0, x1), x2)), w - 1).astype(np.int64)
    miny = np.maximum(np.floor(np.minimum(np.minimum(y0, y1), y2)), 0).astype(np.int64)
    maxy = np.minimum(np.ceil(np.maximum(np.maximum(y0, y1), y2)), h - 1).astype(np.int64)
    ok = (np.abs(area) >= 1e-12) & (minx <= maxx) & (miny <= maxy) & np.isfinite(area)
    bw, bh = maxx - minx + 1, maxy - miny + 1
    span = np.where(ok, np.maximum(bw, bh), 0)
    out = [], [], [], [], [], []
    lo = 0
    groups = []
    for S in _CLASSES:
        sel = np.flatnonzero(ok & (span > lo) & (span <= S))
        lo = S
        step = max(1, _BATCH // (S * S))
        groups += [(sel[c:c + step], S, S) for c in range(0, len(sel), step)]
    groups += [(np.array([t]), int(bw[t]), int(bh[t])) for t in np.flatnonzero(ok & (span > lo))]
    for t, SX, SY in groups:
        gxr, gyr = np.arange(SX), np.arange(SY)
        gx = minx[t, None, None] + gxr[None, None, :]
        gy = miny[t, None, None] + gyr[None, :, None]
        box = (gxr[None, None, :] < bw[t, None, None]) & (gyr[None, :, None] < bh[t, None, None])
        px, py = gx + 0.5, gy + 0.5
        a = area[t, None, None]
        X0, Y0, X1, Y1, X2, Y2 = (v[t, None, None] for v in (x0, y0, x1, y1, x2, y2))
        if test == "bake":  # the texture baker's formula (kept verbatim so bakes stay bit-identical)
            b0 = ((X1 - px) * (Y2 - py) - (Y1 - py) * (X2 - px)) / a
            b1 = ((X2 - px) * (Y0 - py) - (Y2 - py) * (X0 - px)) / a
        else:
            b0 = edge(X1, Y1, X2, Y2, px, py) / a
            b1 = edge(X2, Y2, X0, Y0, px, py) / a
        b2 = 1.0 - b0 - b1 if test != "bake" else 1 - b0 - b1
        if test == "bake":
            inside = box & (b0 >= -1e-6) & (b1 >= -1e-6) & (b2 >= -1e-6)
        elif test == "open":
            eps = 1e-7
            inside = box & (b0 > eps) & (b1 > eps) & (b2 > eps)
        else:
            inside = box & (b0 >= 0) & (b1 >= 0) & (b2 >= 0)
        ti, yi, xi = np.nonzero(inside)
        out[0].append(t[ti])
        out[1].append(gx[ti, 0, xi])
        out[2].append(gy[ti, yi, 0])
        out[3].append(b0[ti, yi, xi])
        out[4].append(b1[ti, yi, xi])
        out[5].append(b2[ti, yi, xi])
    if not out[0]:
        z = np.zeros(0)
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64), z, z, z
    t, px, py, b0, b1, b2 = (np.concatenate(v) for v in out)
    if order == "triangle":
        o = np.lexsort((px, py, t))
        t, px, py, b0, b1, b2 = t[o], px[o], py[o], b0[o], b1[o], b2[o]
    return t, px, py, b0, b1, b2


def rasterize(screen: np.ndarray, key: np.ndarray, normals: np.ndarray, front: np.ndarray, w: int, h: int,
              extra: np.ndarray | None = None) -> Buffers:
    """screen: (m,3,2) pixel coords; key: (m,3) closeness (interpolated linearly);
    normals: (m,3,3) per-corner normals; front: (m,) front-facing flags;
    extra: optional (m,3,k) per-corner attributes (e.g. UVs) interpolated into buf.extra.

    Depth rule: the largest key wins; on a tie the earlier triangle wins (as the former loop did)."""
    buf = Buffers(w, h, 0 if extra is None else extra.shape[2])
    t, px, py, b0, b1, b2 = fragments(screen, w, h)
    if len(t):
        k = b0 * key[t, 0] + b1 * key[t, 1] + b2 * key[t, 2]
        pix = py * w + px
        o = np.lexsort((t, -k, pix))
        first = o[np.r_[True, pix[o][1:] != pix[o][:-1]]]
        t, px, py, b0, b1, b2, k = t[first], px[first], py[first], b0[first], b1[first], b2[first], k[first]
        buf.depth[py, px] = k
        buf.tri[py, px] = t
        buf.normal[py, px] = b0[:, None] * normals[t, 0] + b1[:, None] * normals[t, 1] + b2[:, None] * normals[t, 2]
        buf.front[py, px] = front[t]
        if extra is not None:
            buf.extra[py, px] = b0[:, None] * extra[t, 0] + b1[:, None] * extra[t, 1] + b2[:, None] * extra[t, 2]
    length = np.linalg.norm(buf.normal, axis=2, keepdims=True)
    buf.normal = np.where(length > 1e-12, buf.normal / np.maximum(length, 1e-12), 0)
    return buf


def coverage(tris2d: np.ndarray, w: int, h: int, owner: np.ndarray | None = None):
    """Count how many triangles cover each pixel centre (used for UV overlap).

    tris2d: (m,3,2) pixel coords. Returns (count[h,w], last_owner[h,w])."""
    count = np.zeros((h, w), dtype=np.int32)
    who = np.full((h, w), -1, dtype=np.int64)
    t, px, py, *_ = fragments(tris2d, w, h, test="open")
    if len(t):
        pix = py * w + px
        count.reshape(-1)[:] = np.bincount(pix, minlength=w * h).astype(np.int32)
        last = np.full(w * h, -1, dtype=np.int64)
        np.maximum.at(last, pix, t)  # the loop let the highest triangle index write last
        has = last >= 0
        who.reshape(-1)[has] = last[has] if owner is None else np.asarray(owner)[last[has]]
    return count, who


def draw_lines(img: np.ndarray, segs: np.ndarray, color, depth: np.ndarray | None = None, seg_key: np.ndarray | None = None,
               tol: float = 0.0, alpha: float = 1.0):
    """Draw 2D segments (n,2,2) into img (h,w,3); optional depth test against a closeness buffer.

    Vectorized over all samples. Each segment blends a pixel at most once, and different segments
    blend in rounds (1st segment hitting every pixel, then the 2nd, ...), which reproduces drawing
    the segments one by one exactly."""
    h, w = img.shape[:2]
    color = np.asarray(color, dtype=np.float64)
    segs = np.asarray(segs, dtype=np.float64).reshape(-1, 2, 2)
    if not len(segs):
        return
    x0, y0, x1, y1 = segs[:, 0, 0], segs[:, 0, 1], segs[:, 1, 0], segs[:, 1, 1]
    n = (np.maximum(np.abs(x1 - x0), np.abs(y1 - y0))).astype(np.int64) + 2
    seg = np.repeat(np.arange(len(segs)), n)
    j = np.arange(len(seg)) - np.repeat(np.cumsum(n) - n, n)
    step = 1.0 / (n - 1)
    t = j * step[seg]  # numpy.linspace(0, 1, n): j * (1 / (n - 1)), last sample exactly 1
    t[np.cumsum(n) - 1] = 1.0
    xs = np.round(x0[seg] + (x1 - x0)[seg] * t - 0.5).astype(int)
    ys = np.round(y0[seg] + (y1 - y0)[seg] * t - 0.5).astype(int)
    ok = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
    if depth is not None and seg_key is not None:
        k = seg_key[seg, 0] + (seg_key[seg, 1] - seg_key[seg, 0]) * t
        ok &= np.where(ok, k >= depth[np.clip(ys, 0, h - 1), np.clip(xs, 0, w - 1)] - tol, False)
    xs, ys, seg = xs[ok], ys[ok], seg[ok]
    if not len(xs):
        return
    pix = ys * w + xs
    # one fancy assignment per segment blends a pixel once however often that segment hits it
    _, first = np.unique(seg * (w * h) + pix, return_index=True)
    first.sort()
    xs, ys, pix = xs[first], ys[first], pix[first]
    order = np.argsort(pix, kind="stable")
    sp = pix[order]
    starts = np.r_[0, np.flatnonzero(sp[1:] != sp[:-1]) + 1]
    rank = np.empty(len(pix), dtype=np.int64)
    rank[order] = np.arange(len(pix)) - np.repeat(starts, np.diff(np.r_[starts, len(pix)]))
    if alpha >= 1.0:
        img[ys, xs] = img[ys, xs] * (1 - alpha) + color * alpha
        return
    for r in range(int(rank.max()) + 1):
        sel = rank == r
        yy, xx = ys[sel], xs[sel]
        img[yy, xx] = img[yy, xx] * (1 - alpha) + color * alpha
