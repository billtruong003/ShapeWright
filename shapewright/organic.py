"""Native organic kernel (Phase 22, track G): signed-distance primitives blended into one mesh.

A `blend` shape is an ordered list of SDF items combined into one field (smooth union, subtraction,
intersection), sampled on a regular grid and meshed by marching tetrahedra: each grid cube is split into 6
tetrahedra around its main diagonal (the Kuhn split), so neighbouring cubes agree and the surface is closed
without the case tables of marching cubes. The result is decimated to a triangle budget (as `decimate`),
a decimation that folds or pinches faces is retried at a slightly different ratio, and each face takes the material of the nearest item.
The mesh is then an ordinary part: UVs, bakes, validation, export.

Speed: each item is evaluated only inside its bounding box (plus the blend radius); elsewhere it counts as far
away, which leaves the field's sign, and so the surface, unchanged. G0 measured 2.3 s for the field without this.
"""

from __future__ import annotations

import numpy as np

from . import backend
from .limits import LIMITS, check
from .mesh import Mesh, rotation_matrix

SDF_KINDS = ("sphere", "ellipsoid", "capsule", "cone", "box", "torus")
OPS = ("union", "subtract", "intersect")
FAR = 10.0  # metres: "far outside this item"


# ---------------------------------------------------------------- items


class Item:
    """One SDF primitive in its own frame: centre, rotation, optional mirror (fold x), shell, combine op."""

    def __init__(self, kind: str, args: dict, op: str = "union", blend: float | None = None, mirror: str | None = None,
                 shell: float = 0.0, rotate=None, material: str | None = None, where: str = ""):
        self.kind, self.args, self.op, self.blend, self.mirror = kind, args, op, blend, mirror
        self.shell, self.material, self.where = float(shell), material, where
        self.R = rotation_matrix(rotate)[:3, :3] if rotate is not None and any(rotate) else None
        self.center = np.asarray(args.get("center", [0.0, 0.0, 0.0]), dtype=np.float64)

    # local SDF (centre at origin, no rotation)
    def _local(self, Q: np.ndarray) -> np.ndarray:
        a, k = self.args, self.kind
        if k == "sphere":
            return np.linalg.norm(Q, axis=-1) - a["radius"]
        if k == "ellipsoid":
            r = np.maximum(np.asarray(a["radii"], dtype=np.float64), 1e-6)
            q = Q / r
            k0 = np.linalg.norm(q, axis=-1)
            k1 = np.linalg.norm(q / r, axis=-1)
            return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)
        if k in ("capsule", "cone"):
            pa = np.asarray(a["a"], dtype=np.float64) - self.center
            pb = np.asarray(a["b"], dtype=np.float64) - self.center
            ab = pb - pa
            t = np.clip(((Q - pa) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
            ra = a["radius"] if k == "capsule" else a["radius_a"]
            rb = a["radius"] if k == "capsule" else a["radius_b"]
            return np.linalg.norm(Q - (pa + t[..., None] * ab), axis=-1) - (ra + (rb - ra) * t)
        if k == "box":
            rnd = float(a.get("round", 0.0))
            q = np.abs(Q) - (np.asarray(a["size"], dtype=np.float64) / 2 - rnd)
            return np.linalg.norm(np.maximum(q, 0.0), axis=-1) + np.minimum(q.max(-1), 0.0) - rnd
        if k == "torus":  # around Y
            xz = np.sqrt(Q[..., 0] ** 2 + Q[..., 2] ** 2) - a["radius"]
            return np.sqrt(xz ** 2 + Q[..., 1] ** 2) - a["thickness"]
        raise ValueError(f"unknown sdf '{k}'")

    def __call__(self, P: np.ndarray) -> np.ndarray:
        Q = P.copy()
        if self.mirror:  # fold across the plane through the origin: the item and its mirror image
            ax = "xyz".index(self.mirror)
            Q[..., ax] = np.abs(Q[..., ax])
        Q = Q - self.center
        if self.R is not None:
            Q = Q @ self.R  # inverse rotation (R is orthonormal)
        d = self._local(Q)
        return np.abs(d) - self.shell if self.shell > 0 else d

    def bounds(self) -> np.ndarray:
        """Axis-aligned bounds in the blend frame (mirror included), loose for rotated items."""
        a, k = self.args, self.kind
        if k == "sphere":
            ext = np.full(3, a["radius"])
            lo, hi = -ext, ext
        elif k == "ellipsoid":
            ext = np.max(a["radii"]) * np.ones(3) if self.R is not None else np.asarray(a["radii"], dtype=np.float64)
            lo, hi = -ext, ext
        elif k in ("capsule", "cone"):
            r = a["radius"] if k == "capsule" else max(a["radius_a"], a["radius_b"])
            pa = np.asarray(a["a"], dtype=np.float64) - self.center
            pb = np.asarray(a["b"], dtype=np.float64) - self.center
            lo, hi = np.minimum(pa, pb) - r, np.maximum(pa, pb) + r
        elif k == "box":
            half = np.asarray(a["size"], dtype=np.float64) / 2
            ext = np.full(3, np.linalg.norm(half)) if self.R is not None else half
            lo, hi = -ext, ext
        else:  # torus
            e = a["radius"] + a["thickness"]
            ext = np.full(3, e) if self.R is not None else np.array([e, a["thickness"], e])
            lo, hi = -ext, ext
        lo, hi = lo + self.center - self.shell, hi + self.center + self.shell
        if self.mirror:
            ax = "xyz".index(self.mirror)
            m = max(abs(lo[ax]), abs(hi[ax]))
            lo[ax], hi[ax] = min(-m, lo[ax]), max(m, hi[ax])
        return np.stack([lo, hi])


def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def combine(acc, d, item: Item, k: float):
    if acc is None:
        return d
    if item.op == "union":
        return smin(acc, d, k)
    if item.op == "subtract":
        return -smin(-acc, d, k)
    return -smin(-acc, -d, k)  # intersect


def field(P: np.ndarray, items: list[Item], radius: float, ground: bool = False) -> np.ndarray:
    """The blended field at arbitrary points (no bounding-box shortcut). ground: cut flat at y = 0."""
    acc = None
    for it in items:
        acc = combine(acc, it(P), it, radius if it.blend is None else it.blend)
    return np.maximum(acc, -P[..., 1]) if ground else acc


# ---------------------------------------------------------------- grid + mesher

_CORNERS = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]])
_TETS = np.array([[0, 5, 1, 6], [0, 1, 2, 6], [0, 2, 3, 6], [0, 3, 7, 6], [0, 7, 4, 6], [0, 4, 5, 6]])


def grid_field(items: list[Item], radius: float, voxel: float, ground: bool = False):
    """(F, lo): the field on a grid covering the union items' bounds, each item evaluated inside its own box."""
    adds = [it for it in items if it.op == "union"] or items
    b = np.stack([it.bounds() for it in adds])
    pad = radius + 3 * voxel
    lo, hi = b[:, 0].min(0) - pad, b[:, 1].max(0) + pad
    n = np.floor((hi - lo) / voxel).astype(int) + 2
    check(int(np.prod(n)), LIMITS.max_blend_samples, "blend grid samples (raise voxel)")
    axes = [lo[k] + np.arange(n[k]) * voxel for k in range(3)]
    acc = None
    for it in items:
        k = radius if it.blend is None else it.blend
        ib = it.bounds()
        i0 = np.clip(np.floor((ib[0] - k - 2 * voxel - lo) / voxel).astype(int), 0, n)
        i1 = np.clip(np.ceil((ib[1] + k + 2 * voxel - lo) / voxel).astype(int) + 1, 0, n)
        d = np.full(tuple(n), FAR)
        if np.all(i1 > i0):
            sub = np.stack(np.meshgrid(*[axes[j][i0[j]:i1[j]] for j in range(3)], indexing="ij"), -1)
            d[i0[0]:i1[0], i0[1]:i1[1], i0[2]:i1[2]] = it(sub)
        acc = combine(acc, d, it, k)
    if ground:
        acc = np.maximum(acc, -axes[1][None, :, None])
    return acc, lo


def marching_tets(F: np.ndarray, lo: np.ndarray, h: float) -> Mesh:
    """Zero level set of the grid F (negative inside) as a closed, outward-wound mesh.

    Inside one tetrahedron the interpolated field is linear, so its piece of surface is flat and separates the
    inside corners from the outside ones exactly: each triangle is wound to face from the former to the latter.
    (A gradient test at the triangle centre failed on thin, carved shells.)"""
    F = np.where(F == 0.0, 1e-12, F)  # a sample exactly on the surface would give zero-area triangles
    flat = F.reshape(-1)
    nx, ny, nz = F.shape
    base = (np.arange(nx - 1)[:, None, None] * ny * nz + np.arange(ny - 1)[None, :, None] * nz
            + np.arange(nz - 1)[None, None, :]).reshape(-1)
    off = _CORNERS @ np.array([ny * nz, nz, 1])
    vals = flat[base[:, None] + off[None, :]]
    base = base[(vals < 0).any(1) & (vals >= 0).any(1)]  # cells the surface passes through
    tris, dirs = [], []
    for tet in _TETS:
        ids = base[:, None] + off[tet][None, :]
        inside = flat[ids] < 0
        n_in = inside.sum(1)
        for count in (1, 2, 3):
            sel = n_in == count
            if not sel.any():
                continue
            order = np.argsort(~inside[sel], axis=1, kind="stable")  # inside corners first
            s = np.take_along_axis(ids[sel], order, 1)
            P = np.stack(np.unravel_index(s, F.shape), -1).astype(np.float64)  # (k,4,3) corner grid coords
            out_dir = P[:, count:].mean(1) - P[:, :count].mean(1)  # inside corners -> outside corners
            if count == 1:
                edges = [[(0, 1), (0, 2), (0, 3)]]
            elif count == 3:
                edges = [[(0, 3), (1, 3), (2, 3)]]
            else:
                edges = [[(0, 2), (0, 3), (1, 3)], [(0, 2), (1, 3), (1, 2)]]
            for tri in edges:
                tris.append(np.stack([np.stack([s[:, a], s[:, b]], 1) for a, b in tri], 1))
                dirs.append(out_dir)
    if not tris:
        return Mesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
    E = np.sort(np.concatenate(tris), axis=2)
    D = np.concatenate(dirs)
    keys = E[..., 0] * F.size + E[..., 1]
    uniq, inv = np.unique(keys.reshape(-1), return_inverse=True)
    a, b = uniq // F.size, uniq % F.size
    fa, fb = flat[a], flat[b]
    t = (fa / (fa - fb))[:, None]
    pa = lo + np.stack(np.unravel_index(a, F.shape), 1) * h
    pb = lo + np.stack(np.unravel_index(b, F.shape), 1) * h
    V = pa + (pb - pa) * t
    T = inv.reshape(-1, 3)
    Q = V[T]
    n = np.cross(Q[:, 1] - Q[:, 0], Q[:, 2] - Q[:, 0])
    flip = np.einsum("ij,ij->i", n, D) < 0
    T[flip] = T[flip][:, ::-1]
    # a surface passing (almost) through a grid point gives (almost) coincident vertices on that point's edges:
    # welding them collapses the zero-area triangles cleanly (dropping those triangles would open holes)
    return Mesh(V, T).merged(6)


def collapse_degenerate(m: Mesh, rounds: int = 8) -> Mesh:
    """Collapse the shortest edge of each (near) zero-area face, as the validator measures it, to its midpoint:
    decimation can leave a few collinear needles that welding does not catch."""
    for _ in range(rounds):
        size = float(np.linalg.norm(m.V.max(0) - m.V.min(0)))
        _, area = m.face_normals()
        bad = np.flatnonzero(area < (size * 2e-5) ** 2)
        if not len(bad):
            return m
        V, F = m.V.copy(), m.F.copy()
        done = set()
        for f in bad:
            tri = F[f]
            if len(set(tri.tolist())) < 3 or done & set(tri.tolist()):
                continue
            L = [np.linalg.norm(V[tri[k]] - V[tri[(k + 1) % 3]]) for k in range(3)]
            k = int(np.argmin(L))
            a, b = int(tri[k]), int(tri[(k + 1) % 3])
            V[a] = (V[a] + V[b]) / 2
            F[F == b] = a
            done |= {a, b}
        keep = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
        m = Mesh(V, F[keep]).compacted()
    return m


def pinch_points(m: Mesh) -> list[list[float]]:
    """Midpoints of edges not shared by exactly two faces (where a narrow gap was collapsed), clustered to 5 cm."""
    E = np.sort(np.concatenate([m.F[:, [0, 1]], m.F[:, [1, 2]], m.F[:, [2, 0]]]), axis=1)
    u, c = np.unique(E, axis=0, return_counts=True)
    P = m.V[u[c != 2]].mean(1)
    out: list = []
    for p in P:
        if all(np.linalg.norm(p - q) > 0.05 for q in out):
            out.append(p)
    return [[round(float(x), 3) for x in p] for p in out]


def defects(m: Mesh) -> tuple[int, int]:
    """(edges not shared by exactly two faces, folded faces): (0, 0) for a clean closed mesh. Topology ranks first:
    a hole is an error everywhere, a fold may be a sharp crease."""
    E = np.sort(np.concatenate([m.F[:, [0, 1]], m.F[:, [1, 2]], m.F[:, [2, 0]]]), axis=1)
    _, c = np.unique(E, axis=0, return_counts=True)
    bad = int((c != 2).sum())
    return (bad, 0) if bad else (0, int(folded(m).sum()))


def folded(m: Mesh) -> np.ndarray:
    """Faces folded over by decimation: the normal points against at least two of the three faces across its edges.
    (The field's gradient is no test: across a thin ear the far side's gradient points the other way; nor are
    corner normals: at a cone tip they cancel.)"""
    fn, _ = m.face_normals()
    nf = len(m.F)
    E = np.sort(np.stack([m.F[:, [0, 1]], m.F[:, [1, 2]], m.F[:, [2, 0]]], 1).reshape(-1, 2), axis=1)
    face = np.repeat(np.arange(nf), 3)
    order = np.lexsort((E[:, 1], E[:, 0]))
    E, face = E[order], face[order]
    same = np.all(E[1:] == E[:-1], axis=1)  # consecutive equal edges: the two faces sharing it (closed mesh)
    a, b = face[:-1][same], face[1:][same]
    against = np.einsum("ij,ij->i", fn[a], fn[b]) < -0.5
    count = np.bincount(a[against], minlength=nf) + np.bincount(b[against], minlength=nf)
    return count >= 2


# ---------------------------------------------------------------- the whole thing


def mesh_blend(items: list[Item], radius: float, voxel: float, triangles: int, smooth: int = 0,
               ground: bool = False) -> tuple[Mesh, dict]:
    """Mesh a blend; returns (mesh with per-face material labels, stats)."""
    F, lo = grid_field(items, radius, voxel, ground)
    raw = marching_tets(F, lo, voxel)
    if raw.n_tris == 0:
        raise ValueError("the blend has no surface (every item subtracted, or nothing inside the grid)")
    m = backend.smooth_taubin(raw, smooth, 0.5) if smooth else raw
    stats = {"grid": list(F.shape), "raw_triangles": raw.n_tris, "defects": 0, "folded": 0}
    if m.n_tris > triangles:
        base = triangles / m.n_tris
        best = None
        for f in (1.0, 0.92, 1.08, 0.85, 1.15, 0.8):  # decimation can fold or pinch a few faces; another ratio usually does not
            d = collapse_degenerate(backend.collapse_needles(backend.simplify(m, min(base * f, 1.0))).merged(5))
            bad = defects(d)
            if best is None or bad < best[0]:
                best = (bad, d)
            if bad == (0, 0):
                break
        if best[0][0]:  # quadric decimation pinched a narrow crevice; topology-safe simplification may fit the budget
            c = _closed_to_budget(m, triangles, voxel)
            if c[1].n_tris <= triangles and c[0] < best[0]:
                best = c
        if best[0][0]:
            stats["pinch_at"] = pinch_points(best[1])
            fa = float(best[1].face_normals()[1].mean())
            stats["edge_m"] = float(np.sqrt(4 * fa / np.sqrt(3)))
        (stats["defects"], stats["folded"]), m = best
    if ground:  # decimation moves the flat bottom by micrometres; put it back on the floor
        m.V = m.V.copy()
        m.V[:, 1] = np.maximum(m.V[:, 1], 0.0)
    _label_materials(m, items)
    stats["triangles"] = m.n_tris
    return m, stats


def _closed_to_budget(m: Mesh, triangles: int, voxel: float) -> tuple[tuple[int, int], Mesh]:
    """Manifold simplification (never pinches) with the smallest tolerance found that reaches `triangles`
    (it often cannot: it keeps a crevice the budget has no room for): (defects, mesh)."""
    lo, hi, best = 0.0, voxel * 2, None
    for _ in range(12):
        tol = (lo + hi) / 2
        d = backend.simplify_closed(m, tol)
        if d.n_tris > triangles:
            lo = tol
        else:
            hi, best = tol, d
    if best is None:
        best = backend.simplify_closed(m, voxel * 2)
    return defects(best), best


def _label_materials(m: Mesh, items: list[Item]):
    """Each face takes the material of the nearest union item that names one (unnamed: the part's material)."""
    named = [it for it in items if it.op == "union" and it.material]
    if not named:
        return
    C = m.V[m.F].mean(1)
    cand = [it for it in items if it.op == "union"]
    D = np.abs(np.stack([it(C) for it in cand], 1))  # the item whose own surface is there (inside ones are < 0)
    near = D.argmin(1)
    for i, it in enumerate(cand):
        if it.material:
            sel = near == i
            if sel.any():
                m.set_label("material", it.material, sel)
