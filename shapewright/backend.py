"""Geometry backend boundary.

This is the ONLY module allowed to import third-party geometry libraries
(Manifold, trimesh, scipy, fast-simplification, xatlas). Everything else in the
kernel (shapes, ops, assembler, validators, renderer, exporter) talks to these
functions using :class:`~shapewright.mesh.Mesh`. An architecture test enforces
this (tests/test_architecture.py).

The boundary is deliberately small: operations that are expensive, numerically
delicate or library-specific. Each function states its attribute policy (see
``mesh.POLICY``) so that swapping a library cannot silently drop provenance.

Replacing a backend means re-implementing these functions and re-running the
contract tests; asset sources do not change (see docs/BACKEND.md for what is
and is not backend-independent).
"""

from __future__ import annotations

import numpy as np

from .mesh import Mesh, concat

NAME = "manifold+trimesh"


# ---------------------------------------------------------------- conversions


def as_trimesh(mesh: Mesh):
    import trimesh

    return trimesh.Trimesh(mesh.V, mesh.F, process=False)


def _vprops(meshes: list[Mesh]) -> list[str]:
    return sorted({k for m in meshes for k in m.vattr})


def _to_manifold(mesh: Mesh, vnames: list[str]):
    import manifold3d as mf

    from .mesh import SCHEMA

    cols = [mesh.V]
    for k in vnames:
        cols.append(mesh.vattr[k] if k in mesh.vattr else np.tile(SCHEMA[k].default, (len(mesh.V), 1)))
    props = np.ascontiguousarray(np.concatenate(cols, axis=1).astype(np.float32))
    m = mf.Manifold(mf.Mesh(vert_properties=props, tri_verts=mesh.F.astype(np.uint32),
                            face_id=np.arange(len(mesh.F), dtype=np.uint32)))
    if m.status() != mf.Error.NoError:
        raise ValueError(f"mesh is not a closed manifold ({m.status().name}); this operation needs closed shapes")
    return m.as_original()


def _to_manifold_tracked(mesh: Mesh, vnames: list[str]):
    """As _to_manifold, plus the coplanar-group id of every input triangle.

    After as_original(), Manifold's face_id is a coplanar-group id, not the input
    triangle index (FRESH_AGENT_05). Output faces report that group; _from_manifold
    maps it back to the input triangles of the group."""
    import manifold3d as mf

    m0 = mf.Manifold(mf.Mesh(vert_properties=np.ascontiguousarray(mesh.V.astype(np.float32)), tri_verts=mesh.F.astype(np.uint32),
                             face_id=np.arange(len(mesh.F), dtype=np.uint32)))
    m = _to_manifold(mesh, vnames)
    group = np.empty(len(mesh.F), dtype=np.int64)
    group[np.asarray(m0.to_mesh().face_id, dtype=np.int64)] = np.asarray(m.to_mesh().face_id, dtype=np.int64)  # same triangle order
    return m, group


def _containing(src: Mesh, cand: np.ndarray, P: np.ndarray) -> np.ndarray:
    """For points P on a plane shared by candidate triangles `cand`, the candidate containing each point (closest if none)."""
    A, B, C = (src.V[src.F[cand, k]] for k in range(3))
    v0, v1 = B - A, C - A
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    den = np.where(np.abs(d00 * d11 - d01 * d01) < 1e-30, 1e-30, d00 * d11 - d01 * d01)
    w = P[:, None, :] - A[None]
    d20, d21 = np.einsum("mtk,tk->mt", w, v0), np.einsum("mtk,tk->mt", w, v1)
    bv, bw = (d11 * d20 - d01 * d21) / den, (d00 * d21 - d01 * d20) / den
    inside = np.minimum(np.minimum(bv, bw), 1 - bv - bw)
    return cand[np.argmax(inside, axis=1)]


def _collapse_needles(m: Mesh) -> Mesh:
    """Booleans on dense meshes can leave needle triangles of ~zero area (Phase 10: 2-5 in a
    50k-triangle subtract; Manifold's own simplify leaves some and creates others). Collapse the
    shortest edge of each face below the validator's degenerate threshold, then weld. Meshes without
    such faces are returned unchanged."""
    if not len(m.F):
        return m
    size = float(np.linalg.norm(m.V.max(0) - m.V.min(0))) or 1.0
    thr = (size * 1e-5) ** 2
    for _ in range(4):
        _, area = m.face_normals()
        bad = np.flatnonzero(area < thr)
        if not len(bad):
            return m
        V = m.V.copy()
        va = {k: v.copy() for k, v in m.vattr.items()}
        moved: set = set()
        for f in bad:
            t = m.F[f]
            edges = ((t[1], t[2]), (t[2], t[0]), (t[0], t[1]))
            a, b = min(edges, key=lambda e: float(np.linalg.norm(V[e[0]] - V[e[1]])))
            if a in moved or b in moved:
                continue
            V[b] = V[a]
            for k in va:
                va[k][b] = va[k][a]
            moved.add(b)
        m = Mesh(V, m.F, va, dict(m.fattr), dict(m.cattr), dict(m.labels), set(m.invalidated)).merged()
    return m


def _from_manifold(result, sources: list[tuple[int, Mesh, np.ndarray]], vnames: list[str]) -> Mesh:
    """Rebuild a Mesh from a Manifold result, inheriting face attributes by provenance.

    sources: (original_id, input mesh, coplanar-group id per input triangle)."""
    out = result.to_mesh()
    props = np.asarray(out.vert_properties, dtype=np.float64)
    F = np.asarray(out.tri_verts, dtype=np.int64).reshape(-1, 3)
    offsets = {}
    start = 0
    for oid, m, _ in sources:
        offsets[oid] = start
        start += len(m.F)
    source = concat([m for _, m, _ in sources])
    face_src = np.full(len(F), -1, dtype=np.int64)
    run_index = np.asarray(out.run_index, dtype=np.int64) // 3
    face_id = np.asarray(out.face_id, dtype=np.int64) if out.face_id is not None and len(out.face_id) else None
    by_oid = {oid: (m, g) for oid, m, g in sources}
    for r, oid in enumerate(np.asarray(out.run_original_id, dtype=np.int64)):
        if oid not in offsets or face_id is None:
            continue
        lo, hi = run_index[r], run_index[r + 1]
        m, group = by_oid[oid]
        # signature of each input triangle's face labels: a group whose triangles agree needs no geometry test
        sig = np.unique(np.column_stack([np.asarray(v).reshape(len(m.F), -1) for v in m.fattr.values()] or [np.zeros((len(m.F), 1))]),
                        axis=0, return_inverse=True)[1].reshape(-1)
        order = np.argsort(group, kind="stable")
        starts = np.searchsorted(group[order], face_id[lo:hi])
        first = order[np.minimum(starts, len(order) - 1)]
        ok = group[first] == face_id[lo:hi]
        pick = np.where(ok, first, -1)
        for gid in np.unique(face_id[lo:hi][ok]):
            cand = np.flatnonzero(group == gid)
            if len(cand) > 1 and len(np.unique(sig[cand])) > 1:
                sel = np.flatnonzero(face_id[lo:hi] == gid)
                pick[sel] = _containing(m, cand, props[F[lo + sel], :3].mean(axis=1))
        face_src[lo:hi] = np.where(pick >= 0, offsets[oid] + pick, -1)
    res = source.remapped(props[:, :3], F, face_src, policy="rebuild")
    res = _collapse_needles(res)
    col = 3
    for k in vnames:
        w = source.vattr[k].shape[1]
        res.vattr[k] = props[:, col:col + w]
        res.invalidated.discard(k)
        col += w
    return res


# ---------------------------------------------------------------- solids (policy: rebuild)


def boolean(a: Mesh, b: Mesh, operation: str) -> Mesh:
    """union | difference | intersection. Faces inherit attributes from the input
    face they came from (Manifold provenance); vertex attributes are interpolated;
    corner attributes are invalidated."""
    vn = _vprops([a, b])
    (ma, ga), (mb, gb) = _to_manifold_tracked(a, vn), _to_manifold_tracked(b, vn)
    res = {"union": ma + mb, "difference": ma - mb, "intersection": ma ^ mb}[operation]
    return _from_manifold(res, [(ma.original_id(), a, ga), (mb.original_id(), b, gb)], vn)


def trim(mesh: Mesh, normal, offset: float) -> Mesh:
    """Keep the half-space normal . p >= offset. Cap faces are new (face_src = -1)."""
    vn = _vprops([mesh])
    m, g = _to_manifold_tracked(mesh, vn)
    return _from_manifold(m.trim_by_plane(list(map(float, normal)), float(offset)), [(m.original_id(), mesh, g)], vn)


def min_gap(a: Mesh, b: Mesh, search: float) -> float:
    return float(_to_manifold(a, [])
                 .min_gap(_to_manifold(b, []), search))


def uncovered_volume(a: Mesh, others: list[Mesh]) -> tuple[float, float]:
    """(volume of a, volume of a minus the union of others)."""
    ma = _to_manifold(a, [])
    rest = None
    for o in others:
        mo = _to_manifold(o, [])
        rest = mo if rest is None else rest + mo
    return ma.volume(), (ma - rest).volume() if rest is not None else ma.volume()


def solids(meshes: list[Mesh]) -> list:
    """Convert each mesh to a solid once (None if not a closed manifold), for repeated pairwise
    queries (Phase 10: the assembly validator converted the same parts thousands of times)."""
    out = []
    for m in meshes:
        try:
            out.append(_to_manifold(m, []))
        except ValueError:
            out.append(None)
    return out


def solid_gap(a, b, search: float) -> float:
    return float(a.min_gap(b, search))


def solid_uncovered_volume(a, others: list) -> tuple[float, float]:
    rest = None
    for o in others:
        rest = o if rest is None else rest + o
    return a.volume(), (a - rest).volume() if rest is not None else a.volume()


def is_closed_manifold(mesh: Mesh) -> bool:
    try:
        _to_manifold(mesh, [])
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------- generators (policy: generate)


def convex_hull(points) -> Mesh:
    import trimesh

    h = trimesh.convex.convex_hull(np.asarray(points, dtype=np.float64))
    return Mesh(h.vertices, h.faces)


def box(extents) -> Mesh:
    import trimesh

    t = trimesh.creation.box(extents=np.maximum(np.asarray(extents, dtype=np.float64), 1e-6))
    return Mesh(t.vertices, t.faces)


def box_bounds(bounds) -> Mesh:
    import trimesh

    t = trimesh.creation.box(bounds=np.asarray(bounds, dtype=np.float64))
    return Mesh(t.vertices, t.faces)


def icosphere(subdivisions: int, radius: float) -> Mesh:
    import trimesh

    t = trimesh.creation.icosphere(subdivisions=subdivisions, radius=radius)
    return Mesh(t.vertices, t.faces)


def extrude_polygon(contours: list[np.ndarray], depth: float, scale_top) -> Mesh:
    import manifold3d as mf

    cs = mf.CrossSection([np.asarray(c, dtype=np.float64) for c in contours], mf.FillRule.EvenOdd)
    m = cs.extrude(depth, scale_top=tuple(scale_top)).translate([0, 0, -depth / 2])
    out = m.to_mesh()
    return Mesh(np.asarray(out.vert_properties[:, :3], dtype=np.float64), np.asarray(out.tri_verts, dtype=np.int64))


def revolve_polygon(polygon: np.ndarray, segments: int) -> Mesh:
    import manifold3d as mf

    m = mf.CrossSection([np.asarray(polygon, dtype=np.float64)]).revolve(segments).rotate([-90, 0, 0])  # Z-up -> Y-up
    out = m.to_mesh()
    return Mesh(np.asarray(out.vert_properties[:, :3], dtype=np.float64), np.asarray(out.tri_verts, dtype=np.int64))


# ---------------------------------------------------------------- topology (refine / resample / preserve)


def subdivide_midpoint(mesh: Mesh) -> Mesh:
    """Policy 'refine': each face -> 4; midpoints interpolate vertex and corner attributes."""
    F = mesh.F
    edges = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    uniq, inv = np.unique(edges, axis=0, return_inverse=True)
    inv = inv.reshape(3, -1).T + len(mesh.V)  # midpoint index for edges (01, 12, 20) of each face
    V = np.concatenate([mesh.V, mesh.V[uniq].mean(1)])
    a, b, c = F[:, 0], F[:, 1], F[:, 2]
    ab, bc, ca = inv[:, 0], inv[:, 1], inv[:, 2]
    newF = np.concatenate([np.stack([a, ab, ca], 1), np.stack([ab, b, bc], 1), np.stack([ca, bc, c], 1), np.stack([ab, bc, ca], 1)])
    face_src = np.tile(np.arange(len(F)), 4)
    vsrc = np.concatenate([np.stack([np.arange(len(mesh.V))] * 2, 1), uniq])
    vw = np.concatenate([np.tile([1.0, 0.0], (len(mesh.V), 1)), np.full((len(uniq), 2), 0.5)])
    A, B, C, AB, BC, CA = np.eye(3)[0], np.eye(3)[1], np.eye(3)[2], [0.5, 0.5, 0], [0, 0.5, 0.5], [0.5, 0, 0.5]
    bary_one = [np.array([A, AB, CA]), np.array([AB, B, BC]), np.array([CA, BC, C]), np.array([AB, BC, CA])]
    bary = np.concatenate([np.tile(bb, (len(F), 1, 1)) for bb in bary_one])
    return mesh.remapped(V, newF, face_src, vsrc, vw, bary, policy="refine")


def _transfer(src: Mesh, V, F, policy: str) -> Mesh:
    """Policy 'resample': nearest-face / nearest-vertex attribute transfer."""
    from scipy.spatial import cKDTree

    V = np.asarray(V, dtype=np.float64)
    F = np.asarray(F, dtype=np.int64)
    face_src = cKDTree(src.triangles().mean(1)).query(V[F].mean(1))[1] if len(src.F) else np.full(len(F), -1)
    vert_src = cKDTree(src.V).query(V)[1][:, None]
    return src.remapped(V, F, face_src, vert_src, None, None, policy=policy)


def simplify(mesh: Mesh, ratio: float) -> Mesh:
    import fast_simplification

    V, F = fast_simplification.simplify(mesh.V.astype(np.float32), mesh.F.astype(np.int32), target_reduction=1 - ratio)
    if not mesh.cattr or not len(F):
        return _transfer(mesh, V, F, "resample")
    return _transfer_with_corners(mesh, np.asarray(V, dtype=np.float64), np.asarray(F, dtype=np.int64))


def _point_triangle_dist2(P: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Squared distance from points P (n,3) to triangles T (n,3,3), pairwise (Ericson's closest-point test)."""
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    ab, ac, ap = b - a, c - a, P - a
    d1, d2 = (ab * ap).sum(1), (ac * ap).sum(1)
    bp = P - b
    d3, d4 = (ab * bp).sum(1), (ac * bp).sum(1)
    cp = P - c
    d5, d6 = (ab * cp).sum(1), (ac * cp).sum(1)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2

    def safe(x):
        return np.where(np.abs(x) < 1e-30, 1e-30, x)
    den = safe(va + vb + vc)
    q = a + ab * (vb / den)[:, None] + ac * (vc / den)[:, None]  # interior (lowest precedence)
    # regions in increasing precedence, so the earlier tests of Ericson's sequence win
    e4, e5 = d4 - d3, d5 - d6
    q = np.where(((va <= 0) & (e4 >= 0) & (e5 >= 0))[:, None], b + (c - b) * (e4 / safe(e4 + e5))[:, None], q)
    q = np.where(((vb <= 0) & (d2 >= 0) & (d6 <= 0))[:, None], a + ac * (d2 / safe(d2 - d6))[:, None], q)
    q = np.where(((d6 >= 0) & (d5 <= d6))[:, None], c, q)
    q = np.where(((vc <= 0) & (d1 >= 0) & (d3 <= 0))[:, None], a + ab * (d1 / safe(d1 - d3))[:, None], q)
    q = np.where(((d3 >= 0) & (d4 <= d3))[:, None], b, q)
    q = np.where(((d1 <= 0) & (d2 <= 0))[:, None], a, q)
    return ((P - q) ** 2).sum(1)


def _closest_faces(src: Mesh, P: np.ndarray, k: int = 8) -> np.ndarray:
    """Index of the source face nearest each point: centroid KD-tree for candidates, exact distance to choose."""
    from scipy.spatial import cKDTree

    k = min(k, len(src.F))
    _, cand = cKDTree(src.triangles().mean(1)).query(P, k=k)
    cand = np.asarray(cand).reshape(len(P), k)
    T = src.V[src.F[cand.reshape(-1)]]
    d = _point_triangle_dist2(np.repeat(P, k, 0), T).reshape(len(P), k)
    return cand[np.arange(len(P)), np.argmin(d, 1)]


def _transfer_with_corners(src: Mesh, V: np.ndarray, F: np.ndarray) -> Mesh:
    """Resample keeping corner attributes (UVs): each new face takes one source triangle (the one
    under its centroid) and maps all three corners through it, so a face never straddles two UV
    charts (docs/IMPORT.md). Corners outside the source triangle are extrapolated in its plane."""
    from scipy.spatial import cKDTree

    face_src = _closest_faces(src, V[F].mean(1))
    T = src.V[src.F[face_src]]  # (m, 3, 3) source triangle per new face
    A, e0, e1 = T[:, 0], T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    d00, d01, d11 = (e0 * e0).sum(1), (e0 * e1).sum(1), (e1 * e1).sum(1)
    den = np.where(np.abs(d00 * d11 - d01 * d01) < 1e-30, 1e-30, d00 * d11 - d01 * d01)
    w = V[F] - A[:, None, :]  # (m, 3 corners, 3)
    d20, d21 = np.einsum("mck,mk->mc", w, e0), np.einsum("mck,mk->mc", w, e1)
    b1 = (d11[:, None] * d20 - d01[:, None] * d21) / den[:, None]
    b2 = (d00[:, None] * d21 - d01[:, None] * d20) / den[:, None]
    bary = np.stack([1 - b1 - b2, b1, b2], -1)  # (m, 3 corners, 3 source corners)
    vert_src = cKDTree(src.V).query(V)[1][:, None]
    return src.remapped(V, F, face_src, vert_src, None, bary, policy="resample")


def _edge_users(F: np.ndarray):
    """Undirected edges -> the faces using them, with each face's direction (+1 = low->high vertex)."""
    a, b = F.reshape(-1), F[:, [1, 2, 0]].reshape(-1)
    key = np.minimum(a, b) * (int(F.max()) + 1) + np.maximum(a, b)
    face = np.repeat(np.arange(len(F)), 3)
    sign = np.where(a < b, 1, -1)
    order = np.argsort(key, kind="stable")
    ks = key[order]
    starts = np.r_[0, np.flatnonzero(ks[1:] != ks[:-1]) + 1]
    ends = np.r_[starts[1:], len(ks)]
    return order, starts, ends, face, sign, a, b


def consistent_winding(mesh: Mesh) -> np.ndarray:
    """Boolean mask of faces to flip so each connected shell has consistent winding and closed shells
    face outward (breadth-first over shared edges; no external graph library)."""
    from collections import deque

    F = mesh.F
    m = len(F)
    order, starts, ends, face, sign, _, _ = _edge_users(F)
    nbr: list[list] = [[] for _ in range(m)]
    boundary = np.zeros(m, dtype=bool)
    for s0, e0 in zip(starts, ends):
        users = order[s0:e0]
        if len(users) == 1:
            boundary[face[users[0]]] = True
        elif len(users) == 2:
            u, v = users
            nbr[face[u]].append((face[v], sign[u], sign[v]))
            nbr[face[v]].append((face[u], sign[v], sign[u]))
    o = np.zeros(m, dtype=np.int8)
    flip = np.zeros(m, dtype=bool)
    tri = mesh.V[F]
    vol6 = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2]))
    for seed in range(m):
        if o[seed]:
            continue
        o[seed] = 1
        comp, closed = [seed], not boundary[seed]
        q = deque([seed])
        while q:
            f = q.popleft()
            for g, sf, sg in nbr[f]:
                want = -sf * o[f] * sg  # shared edge must run opposite ways
                if not o[g]:
                    o[g] = want
                    comp.append(g)
                    closed &= not boundary[g]
                    q.append(g)
        comp = np.array(comp)
        if closed and (vol6[comp] * o[comp]).sum() < 0:
            o[comp] = -o[comp]
        flip[comp] = o[comp] < 0
    return flip


def hole_faces(mesh: Mesh) -> np.ndarray:
    """Fan triangles closing each simple boundary loop, wound to match the surrounding faces. (k, 3)."""
    F = mesh.F
    order, starts, ends, face, sign, a, b = _edge_users(F)
    single = order[starts[(ends - starts) == 1]]
    nxt: dict = {}
    for i in single:  # boundary edge as the adjacent face traverses it: a -> b; the hole runs b -> a
        nxt.setdefault(int(b[i]), []).append(int(a[i]))
    out = []
    used: set = set()
    for start in list(nxt):
        if start in used or len(nxt[start]) != 1:
            continue
        loop, v = [start], nxt[start][0]
        while v != start and v in nxt and len(nxt[v]) == 1 and v not in used and len(loop) < 100000:
            loop.append(v)
            v = nxt[v][0]
        if v != start or len(loop) < 3:
            continue
        used.update(loop)
        out += [[loop[0], loop[k], loop[k + 1]] for k in range(1, len(loop) - 1)]
    return np.asarray(out, dtype=np.int64).reshape(-1, 3)


def smooth_taubin(mesh: Mesh, iterations: int, lamb: float) -> Mesh:
    import trimesh

    t = as_trimesh(mesh)
    trimesh.smoothing.filter_taubin(t, lamb=lamb, iterations=iterations)
    return mesh.with_positions(t.vertices)


# ---------------------------------------------------------------- queries


def raycast(mesh: Mesh, origins, directions) -> tuple[np.ndarray, np.ndarray]:
    """Nearest positive hit per ray (Moller-Trumbore). Returns (distance or inf, face or -1)."""
    Orig = np.asarray(origins, dtype=np.float64).reshape(-1, 3)
    D = np.asarray(directions, dtype=np.float64).reshape(-1, 3)
    D = D / np.linalg.norm(D, axis=1, keepdims=True)
    t0, e1, e2 = mesh.V[mesh.F[:, 0]], mesh.V[mesh.F[:, 1]] - mesh.V[mesh.F[:, 0]], mesh.V[mesh.F[:, 2]] - mesh.V[mesh.F[:, 0]]
    best_t = np.full(len(Orig), np.inf)
    best_f = np.full(len(Orig), -1)
    for i in range(len(Orig)):
        p = np.cross(D[i], e2)
        det = np.einsum("ij,ij->i", e1, p)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1), 0)
        s = Orig[i] - t0
        u = np.einsum("ij,ij->i", s, p) * inv
        q = np.cross(s, e1)
        v = (q @ D[i]) * inv
        t = np.einsum("ij,ij->i", e2, q) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-9)
        if hit.any():
            j = np.where(hit, t, np.inf).argmin()
            best_t[i], best_f[i] = t[j], j
    return best_t, best_f


def section_points(mesh: Mesh, axis: int, value: float) -> np.ndarray:
    """Points where the surface crosses the plane coord[axis] == value (for cross-section queries)."""
    T = mesh.triangles()
    pts = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        pa, pb = T[:, a], T[:, b]
        da, db = pa[:, axis] - value, pb[:, axis] - value
        cross = (da * db) < 0
        t = da[cross] / (da[cross] - db[cross])
        pts.append(pa[cross] + (pb[cross] - pa[cross]) * t[:, None])
        on = np.abs(da) < 1e-12
        pts.append(pa[on])
    return np.concatenate(pts) if pts else np.zeros((0, 3))


# ---------------------------------------------------------------- files (policy: generate, with authored attributes)


def load_mesh_file(path, max_triangles: int) -> list[tuple[str, Mesh]]:
    """Load OBJ/GLB/glTF/STL/PLY into (node name, Mesh) with world transforms baked.
    Carries UV0 (corner attribute) and vertex colours when present."""
    import trimesh

    scene = trimesh.load(str(path), force="scene", process=False)
    out = []
    total = 0
    for node in sorted(scene.graph.nodes_geometry):
        T, gname = scene.graph[node]
        g = scene.geometry[gname]
        if not hasattr(g, "faces") or len(g.faces) == 0:
            continue
        total += len(g.faces)
        if total > max_triangles:
            raise ValueError(f"{path.name}: more than {max_triangles} triangles")
        V = np.asarray(g.vertices, dtype=np.float64) @ T[:3, :3].T + T[:3, 3]
        F = np.asarray(g.faces, dtype=np.int64)
        m = Mesh(V, F)
        uv = getattr(g.visual, "uv", None)
        if uv is not None and len(uv) == len(g.vertices):
            m.set_corner("uv", np.asarray(uv, dtype=np.float64)[F])
        vc = getattr(g.visual, "vertex_colors", None)
        if getattr(g.visual, "kind", None) == "vertex" and vc is not None and len(vc) == len(V):
            m.set_vertex("color", np.asarray(vc, dtype=np.float64) / 255.0)
        out.append((str(node), m))
    return out


def load_file_materials(path) -> tuple[dict, list[str]]:
    """Materials of a mesh file: {node: {name, color (linear RGBA), metallic, roughness, emissive (linear RGB),
    alpha_mode, double_sided, images: {channel: PIL image}}} plus glTF extensions the file uses (not imported)."""
    import json as _json
    import struct as _struct

    import trimesh

    scene = trimesh.load(str(path), force="scene", process=False)
    out = {}
    for node in sorted(scene.graph.nodes_geometry):
        _, gname = scene.graph[node]
        g = scene.geometry[gname]
        m = getattr(getattr(g, "visual", None), "material", None)
        if m is None or not hasattr(m, "baseColorFactor"):
            continue

        def fac(v, n, d):
            if v is None:
                return [d] * n
            a = np.asarray(v, dtype=np.float64).reshape(-1)[:n]
            return list(a / 255.0) if a.dtype.kind in "iu" or a.max() > 1.0 else list(a)
        images = {}
        for ch, attr in (("base_color", "baseColorTexture"), ("metallic_roughness", "metallicRoughnessTexture"),
                         ("normal", "normalTexture"), ("occlusion", "occlusionTexture"), ("emissive", "emissiveTexture")):
            img = getattr(m, attr, None)
            if img is not None:
                images[ch] = img
        out[str(node)] = {
            "name": getattr(m, "name", None) or str(gname),
            "color": fac(m.baseColorFactor, 4, 1.0),
            "metallic": 1.0 if m.metallicFactor is None else float(m.metallicFactor),
            "roughness": 1.0 if m.roughnessFactor is None else float(m.roughnessFactor),
            "emissive": None if getattr(m, "emissiveFactor", None) is None else fac(m.emissiveFactor, 3, 0.0),
            "alpha_mode": getattr(m, "alphaMode", None) or "OPAQUE",
            "double_sided": bool(getattr(m, "doubleSided", False)),
            "images": images,
        }
    ext = []
    if str(path).lower().endswith(".glb"):
        blob = open(path, "rb").read(20)
        n = _struct.unpack("<I", blob[12:16])[0]
        with open(path, "rb") as f:
            f.seek(20)
            ext = sorted(_json.loads(f.read(n)).get("extensionsUsed", []))
    return out, ext


def load_scene_summary(path) -> dict:
    """Node names -> (triangle count, bounds) for export round-trip checks."""
    import trimesh

    scene = trimesh.load(str(path), force="scene")
    parents = scene.graph.transforms.parents
    out = {}
    for node in scene.graph.nodes_geometry:
        T, gname = scene.graph[node]
        g = scene.geometry[gname]
        V = np.asarray(g.vertices) @ T[:3, :3].T + T[:3, 3]
        # A mesh with several primitives (a multi-material part) is split by trimesh
        # into child nodes with generated names; fold them back into the glTF node.
        name = str(parents.get(node, node)) if g.metadata.get("from_gltf_primitive") else str(node)
        tris, bounds = len(g.faces), np.stack([V.min(0), V.max(0)])
        if name in out:
            t0, b0 = out[name]
            tris, bounds = t0 + tris, np.stack([np.minimum(b0[0], bounds[0]), np.maximum(b0[1], bounds[1])])
        out[name] = (tris, bounds)
    return out


def connected_components(mesh: Mesh) -> list[np.ndarray]:
    """Face index arrays of edge-connected components (deterministic order)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components as cc

    n = len(mesh.V)
    e = np.concatenate([mesh.F[:, [0, 1]], mesh.F[:, [1, 2]]])
    g = coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n))
    _, lab = cc(g, directed=False)
    flab = lab[mesh.F[:, 0]]
    return [np.flatnonzero(flab == k) for k in dict.fromkeys(flab)]


# ---------------------------------------------------------------- UV


DENSE_UNWRAP_TRIS = 4000


def unwrap_charts(mesh: Mesh, resolution: int, padding: int) -> np.ndarray:
    """Chart + pack one mesh into its own [0,1] square. Returns (m, 3, 2) corner UVs.
    Deterministic: same mesh -> same UVs (tested)."""
    import xatlas

    atlas = xatlas.Atlas()
    atlas.add_mesh(mesh.V.astype(np.float32), mesh.F.astype(np.uint32))
    pack = xatlas.PackOptions()
    pack.resolution = resolution
    pack.padding = padding
    pack.bilinear = True
    pack.rotate_charts = True
    charts = xatlas.ChartOptions()
    if len(mesh.F) > DENSE_UNWRAP_TRIS:
        # xatlas grows very large charts on dense smooth surfaces and spends most of its time
        # doing so (18 s for one 35k-triangle part). Capping chart area relative to the part
        # keeps it at ~2 s with similar packing (docs/PERFORMANCE.md). Low-poly parts are unaffected.
        charts.max_chart_area = float(mesh.area()) / 128
    atlas.generate(charts, pack)
    _, idx, uvs = atlas[0]
    return np.asarray(uvs, dtype=np.float64)[idx]  # xatlas preserves face order
