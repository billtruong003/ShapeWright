"""Multi-hull collision (Phase 21): a few convex hulls that follow the shape, instead of one hull or one per part.

`collision: {mode: hulls, max: 24, exclude: [door_*]}`: every part starts as its own convex hull (a part that is
not convex, like a wall infill around a doorway, is first cut into near-convex pieces); neighbouring clusters are
merged greedily, cheapest first, where the cost is the empty volume the merged hull adds. A merge is refused when
its hull would cover empty space that a probe grid finds outside every piece (an opening: a doorway, a window, the
gap between two blocks), so openings stay open however large the rest of the hull is. Merging stops at `max` hulls
or when only refused merges are left. `exclude` leaves parts out (a door leaf that swings open).
"""

from __future__ import annotations

import fnmatch
import heapq

import numpy as np

from .. import backend
from ..mesh import Mesh

GAP = 0.05  # metres: clusters whose boxes are further apart are never merged


def _hull(points: np.ndarray):
    """(hull vertices, volume, plane equations or None); flat or tiny point sets get a thin-box volume so they still
    merge sensibly."""
    h = backend.hull_planes(points)
    if h is not None:
        return h[0], h[2], h[1]
    ext = np.maximum(points.max(0) - points.min(0), 1e-3)
    return points, float(np.prod(ext)), None


PIECE_WASTE = 0.1  # a split piece may be at most this empty: a looser piece reaches into the opening it surrounds
PIECE_DEPTH = 6


def _pieces(V: np.ndarray, F: np.ndarray, max_waste: float = PIECE_WASTE, depth: int = 0) -> list[np.ndarray]:
    """A part that is not convex (a wall infill around a doorway) split into near-convex pieces: halve it along its
    longest side until each piece's hull is at most `max_waste` empty (closed parts only; PIECE_DEPTH levels)."""
    pts, hv, _ = _hull(V)
    if depth >= PIECE_DEPTH or hv <= 0:
        return [pts]
    vol = backend.closed_volume(Mesh(V, F))
    if vol is None:
        return [pts]
    if hv - vol <= max_waste * hv:
        return [pts]
    lo, hi = V.min(0), V.max(0)
    ax = int(np.argmax(hi - lo))
    mid = (lo[ax] + hi[ax]) / 2
    out = []
    for a, b in ((lo[ax] - 1, mid), (mid, hi[ax] + 1)):  # the two halves, cut by boolean intersection with a box
        blo, bhi = lo - 1, hi + 1
        blo[ax], bhi[ax] = a, b
        try:
            half = backend.boolean(Mesh(V, F), backend.box_bounds(np.stack([blo, bhi])), "intersection")
        except Exception:  # noqa: BLE001 - a failed cut keeps the whole hull
            return [pts]
        if half.n_tris:
            out += _pieces(np.asarray(half.V, dtype=np.float64), np.asarray(half.F), max_waste, depth + 1)
    return out or [pts]


class _Grid:
    """Probe points on a regular grid, looked up by bounding box (index ranges, not a scan of every probe)."""

    def __init__(self, lo, hi, step):
        self.lo, self.step = np.asarray(lo, dtype=np.float64) + step / 2, step
        self.n = np.maximum(np.floor((np.asarray(hi) - self.lo) / step).astype(int) + 1, 1)
        self.empty = np.ones(tuple(self.n), dtype=bool)

    def _box(self, lo, hi):
        i0 = np.clip(np.ceil((np.asarray(lo) - 1e-9 - self.lo) / self.step).astype(int), 0, self.n)
        i1 = np.clip(np.floor((np.asarray(hi) + 1e-9 - self.lo) / self.step).astype(int) + 1, 0, self.n)
        return i0, i1

    def inside(self, eq: np.ndarray | None, lo, hi):
        """Grid indices (k,3) of the empty probes inside the hull with plane equations `eq`, within lo..hi."""
        i0, i1 = self._box(lo, hi)
        if eq is None or np.any(i1 <= i0):
            return np.zeros((0, 3), dtype=int)
        sub = self.empty[i0[0]:i1[0], i0[1]:i1[1], i0[2]:i1[2]]
        idx = np.argwhere(sub)
        if not len(idx):
            return idx
        idx += i0
        P = self.lo + idx * self.step
        return idx[np.all(P @ eq[:, :3].T + eq[:, 3] <= 1e-9, axis=1)]


def decompose(parts, max_hulls: int = 24, exclude: list[str] | None = None, max_waste: float = 0.5,
              max_empty: int = 6) -> list[np.ndarray]:
    """Point sets of the convex hulls (one array per hull). A merge whose hull would be more than `max_waste` empty
    (a doorway between two jambs, the gap between two blocks) is never made, even if that leaves more than
    `max_hulls` hulls: an open doorway matters more than the count."""
    pats = list(exclude or [])
    items = [p for p in parts if not any(fnmatch.fnmatch(p.name, x) or fnmatch.fnmatch(p.base, x) for x in pats)]
    if not items:
        return []
    pts, vol, eqs, lo, hi = [], [], [], [], []
    for p in items:
        for piece in _pieces(np.asarray(p.mesh.V, dtype=np.float64), np.asarray(p.mesh.F)):
            v, w, e = _hull(piece)
            pts.append(v)
            vol.append(w)
            eqs.append(e)
            lo.append(v.min(0))
            hi.append(v.max(0))
    lo, hi = np.array(lo), np.array(hi)
    alive = list(range(len(pts)))
    neighbours = {i: set() for i in alive}
    for i in range(len(pts)):  # boxes within GAP of each other
        close = np.all((lo <= hi[i] + GAP) & (hi >= lo[i] - GAP), axis=1)
        for j in np.flatnonzero(close):
            if j != i:
                neighbours[i].add(int(j))
    heap, version = [], {i: 0 for i in alive}
    # probe grid: points of empty space (inside no piece); a merged hull may cover at most a few of them
    blo, bhi = lo.min(0), hi.max(0)
    step = max(0.15, float(np.linalg.norm(bhi - blo)) / 80)
    grid = _Grid(blo, bhi, step)
    for i in alive:
        k = grid.inside(eqs[i], lo[i], hi[i])
        grid.empty[k[:, 0], k[:, 1], k[:, 2]] = False

    def push(i, j):
        u, w, e = _hull(np.concatenate([pts[i], pts[j]]))
        waste = w - vol[i] - vol[j]
        if waste > max_waste * w or len(grid.inside(e, np.minimum(lo[i], lo[j]), np.maximum(hi[i], hi[j]))) > max_empty:
            return
        heapq.heappush(heap, (waste, i, j, version[i], version[j]))

    for i in alive:
        for j in neighbours[i]:
            if i < j:
                push(i, j)
    count = len(alive)
    live = set(alive)
    while count > max_hulls and heap:
        _, i, j, vi, vj = heapq.heappop(heap)
        if i not in live or j not in live or version[i] != vi or version[j] != vj:
            continue
        pts[i], vol[i], eqs[i] = _hull(np.concatenate([pts[i], pts[j]]))
        lo[i], hi[i] = np.minimum(lo[i], lo[j]), np.maximum(hi[i], hi[j])
        live.discard(j)
        version[i] += 1
        neighbours[i] = (neighbours[i] | neighbours[j]) - {i, j}
        for k in neighbours[j]:
            neighbours[k].discard(j)
            if k != i:
                neighbours[k].add(i)
        count -= 1
        for k in neighbours[i]:
            if k in live:
                push(i, k)
    return [pts[i] for i in sorted(live)]


def segment_clear(hulls: list[np.ndarray], a, b, samples: int = 64) -> bool:
    """True when the segment a-b passes through no hull (a walkable doorway, a clear window)."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    P = a + (b - a) * np.linspace(0, 1, samples)[:, None]
    for h in hulls:
        hp = backend.hull_planes(h)
        if hp is None:
            continue
        eq = hp[1]
        if np.any(np.all(P @ eq[:, :3].T + eq[:, 3] <= 1e-6, axis=1)):
            return False
    return True
